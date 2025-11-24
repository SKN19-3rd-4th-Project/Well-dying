import logging
from typing import TypedDict, Annotated, List, Literal, Dict, Any

# LangChain / LangGraph Imports
from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage, AIMessage
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import ToolNode
from langgraph.graph.message import add_messages

# Custom Modules
from llm_client import LLMClient
from session_manager import SessionManager
from recommend_ba import TOOLS

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ==============================================================================
# [CONSTANTS] System Prompts with In-Context Learning (Few-Shot)
# ==============================================================================

# In-Context Learning을 위한 대화 예시 (Few-shot Data)
# 모델이 따라야 할 '공감 -> 연결 -> 질문/제안'의 패턴을 구체적으로 보여줍니다.
FEW_SHOT_EXAMPLES = """
[대화 예시 1: 무기력함 호소]
User: "요즘은 그냥 침대에만 누워있어. 아무 의미도 없는 것 같고."
AI: "몸도 마음도 많이 무거우신 것 같아요. 하루 종일 누워 계시다 보면 그런 생각이 드실 수 있죠. (공감)
혹시 누워 계시면서 창밖을 보거나, 라디오를 듣는 것처럼 아주 작은 일이라도 편안함을 느낀 순간이 있으셨나요? (탐색 질문)"

[대화 예시 2: 죽음에 대한 두려움]
User: "내가 죽으면 우리 아이들은 어떡하나 걱정이 돼서 잠이 안 와."
AI: "자녀분들 생각에 밤잠을 설치시는군요. 부모님의 깊은 사랑이 느껴져서 저도 마음이 아려옵니다. (공감)
구체적으로 어떤 점이 가장 염려되시는지 여쭤봐도 될까요? 함께 이야기 나누다 보면 마음의 짐을 조금은 덜 수 있을지도 몰라요. (심화 질문)"

[대화 예시 3: 심심함/지루함]
User: "오늘따라 너무 심심하네. 뭐 재미있는 거 없나?"
AI: "적적하신가 봐요. 그런 날에는 기분 전환이 필요하죠! (공감)
거동이 괜찮으시다면, 'recommend_activities_tool'을 통해 집 근처 산책 코스나 집에서 할 수 있는 소일거리를 찾아봐 드릴까요? (활동 제안)"
"""

SYSTEM_PROMPT_TEMPLATE = f"""
당신은 사용자의 삶을 회고하고 남은 날들을 의미 있게 보내도록 돕는 'AI 동반자'입니다.
사용자의 이름은 {{user_name}}이며, 나이는 {{user_age}}입니다.
거동 상태는 '{{user_mobility}}'입니다.

[In-Context Learning 예시]
아래 대화 패턴을 참고하여 답변하세요:
{FEW_SHOT_EXAMPLES}

[대화 원칙]
1. 위 예시처럼 사용자의 감정에 먼저 깊이 공감하고, 따뜻하고 정중한 어조를 유지하세요.
2. 해결책을 섣불리 제시하기보다, 감정을 읽어주는 것을 우선시하세요.
3. 사용자가 심심해하거나 무기력해 보이면 'recommend_activities_tool'을 사용하여 예시처럼 활동을 제안하세요.
4. 대화가 끊기거나 깊은 이야기를 유도해야 한다면 'search_empathy_questions_tool'을 사용하여 적절한 질문을 찾으세요.
5. 대화 종료 시점이 되면, 사용자의 하루를 정리하는 다이어리를 써주겠다고 제안하세요.
"""

INFO_MODE_PROMPT = """
당신은 정확한 행정 및 장례 정보를 제공하는 전문가입니다.
감정적인 위로보다는 정확한 사실(Fact)과 절차를 안내하는 데 집중하세요.
"""

# ==============================================================================
# [LangGraph State] 상태 정의
# ==============================================================================
class AgentState(TypedDict):
    messages: Annotated[List[BaseMessage], add_messages]
    user_profile: Dict[str, Any]
    current_mode: Literal["chat", "info"]

# ==============================================================================
# [Engine Logic] ConversationEngine (구조 및 메서드 보존)
# ==============================================================================
class ConversationEngine:
    def __init__(self, mode):
        self.llm_client = LLMClient()
        self.session_manager = SessionManager()
        self.memory = MemorySaver()
        self.mode = mode
        self.app = self._build_graph()
        self.diary_triggers = ["종료", "그만", "잘자", "내일 봐", "다이어리 써줘"]

    def _build_graph(self):
        workflow = StateGraph(AgentState)
        
        # Nodes
        workflow.add_node("empathy_agent", self._empathy_node)
        workflow.add_node("info_agent", self._info_node)
        workflow.add_node("tools", ToolNode(TOOLS))

        # Edges
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

        return workflow.compile(checkpointer=self.memory)

    # --- Node Methods ---
    def _empathy_node(self, state: AgentState):
        profile = state["user_profile"]
        # 수정된 프롬프트(ICL 포함) 적용
        system_msg = SYSTEM_PROMPT_TEMPLATE.format(
            user_name=profile.get("name", "사용자"),
            user_age=profile.get("age", "미상"),
            user_mobility=profile.get("mobility", "거동 가능")
        )
        model = self.llm_client.get_model_with_tools(TOOLS)
        response = model.invoke([SystemMessage(content=system_msg)] + state["messages"])
        return {"messages": [response]}

    def _info_node(self, state: AgentState):
        model = self.llm_client.get_base_model()
        response = model.invoke([SystemMessage(content=INFO_MODE_PROMPT)] + state["messages"])
        return {"messages": [response]}

    def _route_mode(self, state: AgentState):
        return "info_agent" if state["current_mode"] == "info" else "empathy_agent"

    def _should_continue(self, state: AgentState):
        return "tools" if state["messages"][-1].tool_calls else END

    # --- Diary Logic ---
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

    # --- Public Interface ---
    def process_user_message(self, user_id: str, text: str) -> str:
        # 1. 세션 로드
        session = self.session_manager.load_session(user_id)
        profile = session.get("user_profile", {})
        
        # 2. LangGraph 실행
        config = {"configurable": {"thread_id": user_id}}
        inputs = {
            "messages": [HumanMessage(content=text)],
            "user_profile": profile,
            "current_mode": self.mode
        }
        
        response_text = ""
        for event in self.app.stream(inputs, config=config):
            for k, v in event.items():
                if "messages" in v:
                    msg = v["messages"][-1]
                    if isinstance(msg, AIMessage) and not msg.tool_calls:
                        response_text = msg.content

        # 3. 저장
        self.session_manager.add_message(user_id, "user", text)
        self.session_manager.add_message(user_id, "assistant", response_text)

        # 4. 다이어리 트리거
        if self._check_diary_trigger(text):
            diary = self.generate_diary_summary(user_id)
            response_text += f"\n\n[시스템]: 오늘의 대화를 다이어리로 정리했습니다.\n\n{diary}"

        return response_text

if __name__ == "__main__":
    engine = ConversationEngine()
    print(engine.process_user_message("test_user", "요즘 너무 무기력해서 아무것도 하기 싫어.", mode="chat"))