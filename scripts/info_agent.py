import logging
from langchain_core.messages import SystemMessage

from .llm_client import LLMClient
from chatbot.chatbot_modules.search_info import TOOLS_INFO

logger = logging.getLogger(__name__)

# 프롬프트
INFO_MODE_PROMPT = """
당신은 정확한 행정 및 장례 정보를 제공하는 전문가입니다.
감정적인 위로보다는 정확한 사실(Fact)과 절차를 안내하는 데 집중하세요.
유산상속, 장례 정보(묘지, 봉안당, 화장시설, 자연장지, 장례식장), 정부 지원(화장 장려금, 공영 장례), 디지털 유산 등 포괄적인 정보를 제공합니다.
"""


def info_node(state):
    """정보 제공 모드 에이전트 노드."""
    logger.info(">>> [Agent Active] Info Agent (정보 모드)")

    llm_client = LLMClient()
    model = llm_client.get_model_with_tools(TOOLS_INFO)

    messages = [SystemMessage(content=INFO_MODE_PROMPT)] + state["messages"]
    response = model.invoke(messages)

    return {"messages": [response]}
