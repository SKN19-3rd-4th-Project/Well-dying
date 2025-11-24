import logging
from typing import TypedDict, Annotated, List, Literal, Dict, Any

# LangChain / LangGraph Imports
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import ToolNode
from langgraph.graph.message import add_messages

# Custom Modules
from llm_client import LLMClient
from session_manager import SessionManager
from recommend_ba import TOOLS

# Separated Agents
from empathy_agent import empathy_node
from info_agent import info_node

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# LangGraph 상태 정의 (메세지, 사용자 정보, 현재 모드)
class AgentState(TypedDict):
    # add_messages: 리스트를 덮어쓰지 않고 append(추가)하는 Reducer 함수
    messages: Annotated[List[BaseMessage], add_messages]
    user_profile: Dict[str, Any]
    current_mode: Literal["chat", "info"]

# [Conversaion Engine] 대화의 흐름을 제어하는 메인 클래스
class ConversationEngine:
    def __init__(self):
        self.llm_client = LLMClient()
        self.session_manager = SessionManager()
        self.memory = MemorySaver()
        self.app = self._build_graph()
        self.diary_triggers = ["종료", "그만", "잘자", "내일 봐", "다이어리 써줘"]

    def _build_graph(self):
        workflow = StateGraph(AgentState)

        # 1. Nodes 등록 (분리된 모듈에서 가져온 함수 사용)
        workflow.add_node("empathy_agent", empathy_node)
        workflow.add_node("info_agent", info_node)
        workflow.add_node("tools", ToolNode(TOOLS))

        # 2. Edges & Routing
        # Entry Point: 현재 모드에 따라 시작 노드 결정
        workflow.set_conditional_entry_point(
            self._route_mode,
            {"empathy_agent": "empathy_agent", "info_agent": "info_agent"}
        )

        # Empathy Agent -> Tool 사용 여부 확인
        workflow.add_conditional_edges(
            "empathy_agent",
            self._should_continue,
            {"tools": "tools", END: END}
        )
        workflow.add_edge("tools", "empathy_agent") # 툴 실행 후 다시 에이전트로 복귀
        
        # Info Agent -> 종료 (현재는 단발성)
        workflow.add_edge("info_agent", END)

        return workflow.compile(checkpointer=self.memory)

    # 라우팅
    def _route_mode(self, state: AgentState):
        """State의 current_mode를 확인하여 경로 분기"""
        mode = state.get("current_mode", "chat")
        logger.info(f"[Router] Current Mode: {mode}")
        if mode == "info":
            return "info_agent"
        return "empathy_agent"

    def _should_continue(self, state: AgentState):
        """Tool Call 존재 여부 확인"""
        last_message = state["messages"][-1]
        if last_message.tool_calls:
            return "tools"
        return END

    # 다이어리 생성
    def generate_diary_summary(self, user_id: str) -> str:
        history_text = self.session_manager.export_user_history(user_id)
        prompt = f"""
        당신은 사용자의 하루를 따뜻하게 기록해주는 '회고록 작가'입니다.
        아래 대화 기록을 바탕으로, 사용자의 기분과 있었던 일을 3~5문장의 '오늘의 다이어리' 형식으로 작성해주세요.
        
        [대화 기록]
        {history_text}
        """
        return self.llm_client.generate_text("당신은 에세이 작가입니다.", prompt)

    def _check_diary_trigger(self, text: str) -> bool:
        return any(trigger in text for trigger in self.diary_triggers)

    # Public Interface
    def process_user_message(self, user_id: str, text: str, mode: str = "chat") -> str:
        """
        [Main Interface]
        UI에서 사용자가 선택한 mode(토글 상태)를 인자로 받습니다.
        """
        # 1. 세션 로드
        session = self.session_manager.load_session(user_id)
        profile = session.get("user_profile", {})
        
        # 2. LangGraph 실행 입력값 구성
        # UI에서 전달받은 mode를 State에 주입합니다.
        config = {"configurable": {"thread_id": user_id}}
        inputs = {
            "messages": [HumanMessage(content=text)],
            "user_profile": profile,
            "current_mode": mode 
        }
        
        response_text = ""
        
        # 3. 그래프 스트리밍 실행
        try:
            for event in self.app.stream(inputs, config=config):
                for k, v in event.items():
                    if "messages" in v:
                        msg = v["messages"][-1]
                        if isinstance(msg, AIMessage) and not msg.tool_calls:
                            response_text = msg.content
        except Exception as e:
            logger.error(f"Error during graph execution: {e}")
            return "시스템 오류가 발생했습니다."

        # 4. 대화 내용 저장
        self.session_manager.add_message(user_id, "user", text)
        self.session_manager.add_message(user_id, "assistant", response_text)

        # 5. 다이어리 트리거 확인
        if self._check_diary_trigger(text):
            diary = self.generate_diary_summary(user_id)
            response_text += f"\n\n[시스템]: 대화를 마무리하며 오늘의 다이어리를 작성했습니다.\n\n{diary}"
            # 종료 시 마지막 방문 시간 업데이트
            self.session_manager.update_last_visit(user_id)

        return response_text