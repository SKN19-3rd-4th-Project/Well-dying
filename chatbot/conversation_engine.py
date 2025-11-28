import logging
from typing import TypedDict, Annotated, List, Literal, Dict, Any
from datetime import datetime

# LangChain / LangGraph Imports
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import ToolNode
from langgraph.graph.message import add_messages

# Custom Modules
from chatbot_modules.llm_client import LLMClient
from chatbot_modules.session_manager import SessionManager
from chatbot_modules.recommend_ba import TOOLS

# Separated Agents
from chatbot_modules.empathy_agent import empathy_node
from chatbot_modules.info_agent import info_node

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ==============================================================================
# [LangGraph State] 상태 정의
# ==============================================================================
class AgentState(TypedDict):
    messages: Annotated[List[BaseMessage], add_messages]
    user_profile: Dict[str, Any]
    current_mode: Literal["chat", "info"]
    seriousness_score: float 

# ==============================================================================
# [Main Class] ConversationEngine
# ==============================================================================
class ConversationEngine:
    def __init__(self):
        self.llm_client = LLMClient()
        self.session_manager = SessionManager()
        self.memory = MemorySaver()
        self.app = self._build_graph()
        
        # 다이어리 생성 대기 플래그 (UI 버튼 시뮬레이션용)
        self.waiting_for_diary_confirm = False

    def _build_graph(self):
        workflow = StateGraph(AgentState)

        # 1. Nodes
        workflow.add_node("empathy_agent", empathy_node)
        workflow.add_node("info_agent", info_node)
        workflow.add_node("tools", ToolNode(TOOLS))

        # 2. Edges
        workflow.set_conditional_entry_point(
            self._route_mode,
            {"empathy_agent": "empathy_agent", "info_agent": "info_agent"}
        )

        workflow.add_conditional_edges(
            "empathy_agent",
            self._should_continue,
            {"tools": "tools", END: END}
        )
        workflow.add_edge("tools", "empathy_agent")
        workflow.add_edge("info_agent", END)

        workflow.add_conditional_edges(
            "info_agent",
            self._should_continue,
            {"tools": "tools", END: END}
        )

        workflow.add_conditional_edges(
            "tools",
            self._route_after_tool,
            {"empathy_agent": "empathy_agent", "info_agent": "info_agent"}
        )

        return workflow.compile(checkpointer=self.memory)

    # --- Routing Logic ---
    def _route_mode(self, state: AgentState):
        mode = state.get("current_mode", "chat")
        if mode == "info": return "info_agent"
        return "empathy_agent"

    def _should_continue(self, state: AgentState):
        if state["messages"][-1].tool_calls:
            return "tools"
        return END
        
    def _route_after_tool(self, state: AgentState):
        mode = state.get("current_mode", "chat")
        if mode == "info": return "info_agent"
        return "empathy_agent"

    # --------------------------------------------------------------------------
    # [Feature] Diary Logic (Updated)
    # --------------------------------------------------------------------------
    def generate_diary_summary(self, user_id: str) -> str:
        """
        오늘의 대화 내용을 요약하여 다이어리를 생성합니다.
        기존에 작성된 다이어리가 있다면 내용을 통합합니다.
        """
        # 1. 오늘 날짜 및 사용자 정보 확인
        today_str = datetime.now().strftime("%Y-%m-%d")
        display_date = datetime.now().strftime("%Y/%m/%d")
        
        session = self.session_manager.load_session(user_id)
        user_name = session["user_profile"].get("name", "회원")
        
        # 2. 데이터 준비
        # - 오늘의 대화 내역
        chat_history = self.session_manager.export_user_history(user_id)
        # - 이미 저장된 오늘의 다이어리 (있다면)
        existing_diary = self.session_manager.get_diary_entry(user_id, today_str)
        
        # 3. 프롬프트 구성 (요청된 형식 적용)
        prompt = f"""
        당신은 사용자의 하루를 따뜻하고 아름다운 언어로 기록해주는 '감성 회고록 작가'입니다.
        제공된 [이전 다이어리 내용]과 [오늘의 추가 대화]를 종합하여, 오늘 하루를 정리하는 **하나의 완성된 에세이**를 작성해주세요.

        [작성 대상]
        - 사용자 이름: {user_name}
        - 날짜: {display_date}

        [작성 원칙]
        1. **형식:** - 맨 첫 줄에는 반드시 `[{display_date}]` 날짜 헤더만 적으세요.
           - 각 문장 사이에는 **반드시 두 번 줄바꿈(엔터 두 번)**을 넣어, 문단 사이에 빈 줄이 생기도록 하세요. (가독성 필수)
        
        2. **어조 및 태도:**
           - 사용자를 '{user_name}님'이라고 지칭하며, 곁에서 지켜본 동반자가 따뜻하게 말을 건네는 듯한 어조(~했어요, ~했답니다)를 사용하세요.
           - 단순한 사실 나열("밥을 먹었다")보다는, 그 순간의 **감정과 의미**("따뜻한 밥 한 끼로 마음을 채우셨어요")에 집중하세요.
           - 삶의 마지막을 준비하거나 외로움을 느끼는 분들에게 위로와 평온함을 줄 수 있도록 부드럽고 품격 있는 문체를 유지하세요.

        3. **내용 통합:**
           - [이전 다이어리 내용]이 있다면, [오늘의 추가 대화]와 자연스럽게 연결하여 하나의 흐름으로 만드세요. (내용 중복 금지)
           - 사용자가 느꼈던 주요 감정(우울, 기쁨, 평온 등)과 그에 대한 챗봇의 공감, 추천받은 활동, 사용자의 반응을 중심으로 서술하세요.
           - 마지막 문장은 내일에 대한 잔잔한 희망이나, 오늘 밤의 평안을 비는 문구로 마무리하세요.

        [이전 다이어리 내용]
        {existing_diary if existing_diary else "(없음)"}

        [오늘의 추가 대화]
        {chat_history}
        """
        
        # 4. LLM 생성
        diary_content = self.llm_client.generate_text("당신은 에세이 작가입니다.", prompt)
        
        # 5. 저장
        self.session_manager.save_diary_entry(user_id, today_str, diary_content)
        
        return diary_content

    def _check_diary_trigger(self, text: str) -> bool:
        """
        UI 버튼('다이어리') 클릭을 시뮬레이션
        사용자가 '다이어리'라고 입력하면 버튼을 누른 것으로 간주
        """
        return text.strip() == "다이어리"

    # --- Public Interface ---
    def process_user_message(self, user_id: str, text: str, mode: str = "chat") -> str:
        # [NEW] 1. 다이어리 생성 확인 단계 (Y/N)
        if self.waiting_for_diary_confirm:
            if text.lower() in ['y', 'yes', '네', '응']:
                self.waiting_for_diary_confirm = False
                return self.generate_diary_summary(user_id)
            else:
                self.waiting_for_diary_confirm = False
                return "다이어리 생성을 취소했습니다. 대화를 계속할까요?"

        # 2. 다이어리 버튼(키워드) 트리거 확인
        if self._check_diary_trigger(text):
            self.waiting_for_diary_confirm = True
            return "오늘 나눈 대화로 다이어리를 생성할까요? (Y/N)"

        # 3. 일반 대화 처리 (LangGraph)
        session = self.session_manager.load_session(user_id)
        profile = session.get("user_profile", {})
        
        config = {"configurable": {"thread_id": user_id}}
        inputs = {
            "messages": [HumanMessage(content=text)],
            "user_profile": profile,
            "current_mode": mode
        }
        
        response_text = ""
        try:
            for event in self.app.stream(inputs, config=config):
                for k, v in event.items():
                    if "messages" in v:
                        msg = v["messages"][-1]
                        if isinstance(msg, AIMessage) and not msg.tool_calls:
                            response_text = msg.content
        except Exception as e:
            logger.error(f"Error: {e}")
            return "오류가 발생했습니다."

        # 4. 대화 저장 (다이어리 소스)
        self.session_manager.add_message(user_id, "user", text)
        self.session_manager.add_message(user_id, "assistant", response_text)

        # (기존의 자동 트리거 로직은 제거하거나 _check_diary_trigger를 위쪽 수동 트리거로 통합했으므로 생략)
        
        return response_text