import logging
from datetime import datetime, timedelta
from typing import TypedDict, Annotated, List, Literal, Dict, Any

from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langgraph.graph.message import add_messages
from langchain_core.messages import SystemMessage, ToolMessage

from .llm_client import LLMClient
from .session_manager import SessionManager
from .recommend_ba import TOOLS
from chatbot.chatbot_modules.search_info import TOOLS_INFO

from .empathy_agent import empathy_node
from .info_agent import info_node

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AgentState(TypedDict):
    """LangGraph state definition."""

    messages: Annotated[List[BaseMessage], add_messages]
    user_profile: Dict[str, Any]
    current_mode: Literal["chat", "info"]
    user_id: str
    recent_texts: List[str]


class ConversationEngine:
    """Main controller that wires empathy/info agents with tool calling."""

    WELCOME_COOLDOWN_MINUTES = 30

    def __init__(self):
        self.llm_client = LLMClient()
        self.session_manager = SessionManager()
        self.app = self._build_graph()

    def _build_graph(self):
        workflow = StateGraph(AgentState)

        workflow.add_node("empathy_agent", empathy_node)
        workflow.add_node("info_agent", info_node)
        workflow.add_node("tools", ToolNode(TOOLS))
        workflow.add_node("info_tools", ToolNode(TOOLS_INFO))

        workflow.set_conditional_entry_point(
            self._route_mode,
            {"empathy_agent": "empathy_agent", "info_agent": "info_agent"},
        )

        workflow.add_conditional_edges(
            "empathy_agent",
            self._should_continue,
            {"tools": "tools", END: END},
        )
        workflow.add_edge("tools", "empathy_agent")

        workflow.add_conditional_edges(
            "info_agent",
            self._should_continue,
            {"info_tools": "info_tools", END: END},
        )
        workflow.add_edge("info_tools", "info_agent")

        return workflow.compile()

    def _route_mode(self, state: AgentState):
        """Route to empathy/info agent based on mode."""
        mode = state.get("current_mode", "chat")
        logger.info(f"[Router] Current Mode: {mode}")
        if mode == "info":
            return "info_agent"
        return "empathy_agent"

    def _should_continue(self, state: AgentState):
        """Decide whether to invoke tools."""
        last_message = state["messages"][-1]
        if last_message.tool_calls:
            return "tools"
        return END

    def _should_show_welcome(self, session: Dict[str, Any], mode: str) -> bool:
        """Return True when a stored session is revisited after a cooldown."""
        if mode != "chat":
            return False
        last_visit = session.get("last_visit")
        history = session.get("conversation_history", [])
        if not last_visit or not history:
            return False
        try:
            last_dt = datetime.fromisoformat(last_visit)
        except Exception:
            return False
        return datetime.now() - last_dt > timedelta(minutes=self.WELCOME_COOLDOWN_MINUTES)

    def process_user_message(self, user_id: str, text: str, mode: str = "chat") -> str:
        """
        Primary entry point used by the API.
        """
        session = self.session_manager.load_session(user_id)
        profile = session.get("user_profile", {})
        welcome_text = None
        if self._should_show_welcome(session, mode):
            welcome_text = self.session_manager.get_welcome_message(user_id)
        # 최근 대화 기록을 LangGraph/툴로 전달해 맥락을 유지한다.
        history_messages: List[BaseMessage] = []
        recent_texts: List[str] = []
        for m in session.get("conversation_history", [])[-8:]:
            if not isinstance(m, dict) or "role" not in m or "content" not in m:
                continue
            role = m["role"]
            content = m["content"]
            if role == "user":
                history_messages.append(HumanMessage(content=content))
            elif role == "assistant":
                history_messages.append(AIMessage(content=content))
            recent_texts.append(content)

        config = {"configurable": {"thread_id": user_id}}
        inputs = {
            "messages": history_messages + [HumanMessage(content=text)],
            "user_profile": profile,
            "current_mode": mode,
            "user_id": user_id,
            "recent_texts": recent_texts,
        }

        response_text = ""

        # INFO 모드는 수동으로 툴콜 처리해 OpenAI 400 오류를 방지
        if mode == "info":
            response_text = self._run_info_flow(profile, text, user_id, history_messages)
            self.session_manager.add_message(user_id, "user", text)
            self.session_manager.add_message(user_id, "assistant", response_text)
            self.session_manager.update_last_visit(user_id)
            return response_text

        try:
            for event in self.app.stream(inputs, config=config):
                for _, v in event.items():
                    if "messages" in v:
                        msg = v["messages"][-1]
                        if isinstance(msg, AIMessage) and not msg.tool_calls:
                            response_text = msg.content
        except Exception as e:
            logger.error(f"Error during graph execution: {e}")
            return "시스템 오류가 발생했습니다."

        self.session_manager.add_message(user_id, "user", text)
        if welcome_text:
            response_text = f"{welcome_text}\n\n{response_text}" if response_text else welcome_text
        self.session_manager.add_message(user_id, "assistant", response_text)
        self.session_manager.update_last_visit(user_id)

        return response_text

    def _run_info_flow(
        self,
        profile: Dict[str, Any],
        text: str,
        user_id: str,
        history_messages: List[BaseMessage],
    ) -> str:
        """
        Manual tool-call loop for info mode to ensure tool messages are returned.
        """
        llm = self.llm_client.get_model_with_tools(TOOLS_INFO)
        tools_by_name = {t.name: t for t in TOOLS_INFO}

        system_prompt = (
            "당신은 정확한 행정 및 장례 정보를 제공하는 전문가입니다. "
            "사실과 절차 위주로, 필요한 경우 제공된 도구를 활용해 검색하세요."
        )

        # 1차 호출
        messages: List[BaseMessage] = [SystemMessage(content=system_prompt)] + history_messages + [
            HumanMessage(content=text)
        ]
        ai_msg: AIMessage = llm.invoke(messages)

        if not ai_msg.tool_calls:
            return ai_msg.content

        # 툴 실행 후 재호출
        tool_messages: List[ToolMessage] = []
        for call in ai_msg.tool_calls:
            name = call.get("name")
            args = call.get("args", {}) if isinstance(call, dict) else {}
            tool = tools_by_name.get(name)
            if not tool:
                tool_messages.append(
                    ToolMessage(
                        content=f"'{name}' 도구를 찾을 수 없습니다.",
                        tool_call_id=call.get("id", ""),
                    )
                )
                continue
            try:
                result = tool.invoke(args)
            except Exception as e:
                result = f"도구 실행 실패: {e}"
            tool_messages.append(
                ToolMessage(
                    content=str(result),
                    tool_call_id=call.get("id", ""),
                )
            )

        messages += [ai_msg] + tool_messages
        final_ai: AIMessage = llm.invoke(messages)
        return final_ai.content
