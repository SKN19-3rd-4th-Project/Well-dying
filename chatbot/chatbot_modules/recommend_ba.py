import os
import json
import logging
import random

# Pinecone & LangChain
from pinecone import Pinecone
from langchain_openai import OpenAIEmbeddings
from langchain_core.tools import tool
from langchain_tavily import TavilySearch

# 연결 상태 로깅
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# max_results=3: 속도와 토큰 절약을 위해 상위 3개만 검색
tavily_search = TavilySearch(max_results=3)
tavily_search.name = "search_realtime_info_tool"
tavily_search.description = """
[Tool] 최신 뉴스, 날씨, 현재 트렌드 등 '실시간 정보'가 필요할 때 웹에서 검색합니다.
위로가 필요한 일반적인 대화나, 철학적인 질문에는 **절대** 사용하지 마세요.
사용자가 '요즘 날씨', '오늘 날씨', '오늘 뉴스', '날씨', '뉴스' 정보를 구체적으로 말할 때만 사용하세요.
"""

# 데이터 파일 경로
current_dir = os.path.dirname(os.path.abspath(__file__))
file_path = os.path.join(current_dir, '..', '..', 'data', 'processed', 'conversation_rules.json')

# 설정
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
TALK_INDEX_NAME = "talk-assets"
WISDOM_INDEX_NAME = "welldying-wisdom"
EMBEDDING_MODEL = "text-embedding-3-small"

# 전역 객체 초기화
try:
    pc = Pinecone(api_key=PINECONE_API_KEY)
    embeddings = OpenAIEmbeddings(model=EMBEDDING_MODEL)
except Exception as e:
    logger.warning(f"Pinecone 초기화 실패: {e}")
    index = None

# 대화 규칙
with open(file_path, 'r', encoding='utf-8') as f:
    RULES = json.load(f)

@tool
def recommend_activities_tool(user_emotion: str, mobility_status: str = "거동 가능") -> str:
    """
    [Tool] 사용자의 감정과 거동 상태를 기반으로 '의미 있는 활동'을 추천합니다.
    사용자가 심심해하거나, 무기력하거나, 기분 전환이 필요할 때 호출하세요.
    """
    index = pc.Index(TALK_INDEX_NAME)
    if not index: 
        return "DB 연결 오류"

    print("[Tool: 활동 추천]")

    # 1. Logic: 감정 -> 태그 매핑
    mappings = RULES.get("mappings", {})
    
    target_tags = []
    for key, tags in mappings.get("emotion_to_feeling_tags", {}).items():
        if key in user_emotion: target_tags.extend(tags)
    if not target_tags: target_tags = ["평온/이완"]

    energy_limit = 5
    for key, val in mappings.get("mobility_to_energy_range", {}).items():
        if key in mobility_status:
            energy_limit = val.get("max_energy", 5)

    # 2. RAG: Pinecone Search
    query = f"효과: {', '.join(target_tags)}인 활동"
    vec = embeddings.embed_query(query)
    
    res = index.query(
        vector=vec, 
        top_k=10,
        include_metadata=True, 
        filter={"type": {"$eq": "activity"}, "ENERGY_REQUIRED": {"$lte": energy_limit}}
    )

    matches = res.get('matches', [])
    if not matches: 
        return "적절한 활동을 찾지 못했습니다."
    
    selected_matches = random.sample(matches, min(len(matches), 3))

    results = []
    for m in selected_matches:
        meta = m['metadata']
        results.append(f"- {meta.get('activity_kr')} (기대효과: {meta.get('FEELING_TAGS')})")
    
    print("[Tool] 검색 결과\n", results)
    return "\n".join(results)

@tool
def search_empathy_questions_tool(context: str) -> str:
    """
    [Tool] 대화 맥락에 맞는 '공감 질문'을 검색합니다.
    사용자의 말을 더 깊이 듣고 싶거나 대화가 막혔을 때 호출하세요.
    """
    index = pc.Index(TALK_INDEX_NAME)
    if not index: 
        return "DB 연결 오류"
    
    vec = embeddings.embed_query(context)
    res = index.query(
        vector=vec, 
        top_k=3, 
        include_metadata=True, 
        filter={"type": {"$eq": "question"}}
    )
    
    # In-Context Learning 유도
    questions = [f"- {m['metadata'].get('question_text')} (의도: {m['metadata'].get('intent')})" for m in res['matches']]
    
    print(f"[Tool 질문]\n {questions}")
    return "\n".join(questions) if questions else "적절한 질문이 없습니다."

@tool
def search_welldying_wisdom_tool(topic: str) -> str:
    """
    [Tool] 죽음, 삶의 의미, 상실 등 깊이 있고 철학적인 주제에 대한 지혜를 검색합니다.
    사용자의 진지함 점수가 높거나, 심오한 질문을 던졌을 때 사용하세요.
    
    Args:
        topic (str): 검색할 주제 키워드 (예: "죽음의 의미", "후회 없는 삶", "용서")
    """
    index = pc.Index(WISDOM_INDEX_NAME)
    if not index: 
        return "지혜 DB 연결 오류"
    
    logger.info(f"지식 검색 요청: {topic}")
    
    vec = embeddings.embed_query(topic)
    
    # DB에 type='wisdom'으로 데이터를 적재해두었다고 가정
    res = index.query(
        vector=vec, 
        top_k=3, 
        include_metadata=True, 
        filter={"type": {"$eq": "wisdom"}}
    )
    
    matches = res.get('matches', [])
    if not matches:
        return "관련된 명언을 찾지 못했습니다. 보편적인 인류의 지혜로 답변해주세요."
    
    results = []
    for m in matches:
        meta = m['metadata']
        # content: 본문, source: 출처
        results.append(f"내용: {meta.get('content', '')}\n출처: {meta.get('source', 'Unknown')}")
    
    print("[Tool 지식 검색]", results)
    return "\n---\n".join(results)

# 외부 모듈에서 import 할 수 있도록 TOOLS 리스트 정의
TOOLS = [recommend_activities_tool, search_empathy_questions_tool, search_welldying_wisdom_tool]

# Tavily 검색이 유효할 때만 추가
if tavily_search:
    TOOLS.append(tavily_search)