import logging
from langchain_core.messages import AIMessage

logger = logging.getLogger(__name__)

# 프롬프트
# ==============================================================================
INFO_MODE_PROMPT = """
당신은 정확한 행정 및 장례 정보를 제공하는 전문가입니다.
감정적인 위로보다는 정확한 사실(Fact)과 절차를 안내하는 데 집중하세요.
"""
# ==============================================================================

def info_node(state):
    """
    정보 제공 모드 에이전트 노드 (Placeholder)
    """
    logger.info(">>> [Agent Active] Info Agent (정보 모드)")
    
    # 현재는 단순히 정보 모드임을 알리는 텍스트 반환
    # 추후 로직 추가 예정
    
    return {
        "messages": [
            AIMessage(content="[정보 모드] 현재 정확한 정보를 제공하기 위해 시스템을 준비 중입니다. 궁금한 법률/장례 절차를 말씀해 주세요.")
        ]
    }