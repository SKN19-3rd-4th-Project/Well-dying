import logging
from typing import TypedDict, Annotated, List, Literal, Dict, Any

# LangChain / LangGraph
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import ToolNode
from langgraph.graph.message import add_messages

# Custom
from .chatbot_modules.llm_client import LLMClient
from .chatbot_modules.session_manager import SessionManager
from .chatbot_modules.recommend_ba import TOOLS
from .chatbot_modules.diary_manager import DiaryManager

# Agents
from .chatbot_modules.empathy_agent import empathy_node
from .chatbot_modules.info_agent import info_node

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
# [Main] ConversationEngine
# ==============================================================================
class ConversationEngine:
    def __init__(self):
        self.llm_client = LLMClient()
        self.session_manager = SessionManager()
        self.memory = MemorySaver()
        self.diary_manager = DiaryManager()

        self.app = self._build_graph()
        self.waiting_for_diary_confirm = False # [테스트] 다이어리 생성 대기 플래그 (UI 버튼 시뮬레이션용)

    # --------------------------------------------------------------------------
    # Graph Logic
    # --------------------------------------------------------------------------
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

    # --------------------------------------------------------------------------
    # Routing Logic
    # --------------------------------------------------------------------------
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
        if mode == "info": 
            return "info_agent"
        return "empathy_agent"

    # --------------------------------------------------------------------------
    # Diary Logic
    # --------------------------------------------------------------------------
    def generate_diary_summary(self, user_id: str) -> str:
        """
        오늘의 대화 내용을 요약하여 다이어리를 생성합니다.
        기존에 작성된 다이어리가 있다면 내용을 통합합니다.
        """
        return self.diary_manager.create_diary_for_today(user_id)
    
    # 다이어리 생성 트리거 -> UI상에서 다이어리탭을 누른 것으로 간주
    def _check_diary_trigger(self, text: str) -> bool:
        return text.strip() == "다이어리"

    # --------------------------------------------------------------------------
    # Chat Logic
    # --------------------------------------------------------------------------
    def process_user_message(self, user_id: str, text: str, mode: str = "chat") -> str:
        # --- 다이어리 ---
        # 생성 확인 (Y/N)
        if self.waiting_for_diary_confirm:
            if text.lower() in ['y', 'yes', '네', '응']:
                self.waiting_for_diary_confirm = False
                
                # 생성 전 대화 내용 확인 (Manager 내부에서도 체크하지만, 여기서도 빠른 피드백을 위해)
                chat_history = self.session_manager.export_user_history(user_id)
                if not chat_history or chat_history == "오늘 나눈 대화가 없습니다.":
                    return "오늘 나눈 대화가 없어 다이어리를 생성할 수 없습니다."
                
                return self.generate_diary_summary(user_id)
            else:
                self.waiting_for_diary_confirm = False
                return "다이어리 생성을 취소했습니다. 대화를 계속할까요?"

        # 다이어리 버튼 트리거 확인
        if self._check_diary_trigger(text):
            self.waiting_for_diary_confirm = True
            return "오늘 나눈 대화로 다이어리를 생성할까요? (Y/N)"

        # --- 일반 대화 처리 ---
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

        # 대화 저장 (다이어리 소스)
        self.session_manager.add_message(user_id, "user", text)
        self.session_manager.add_message(user_id, "assistant", response_text)

        return response_text