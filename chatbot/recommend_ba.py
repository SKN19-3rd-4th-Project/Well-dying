import os
import json
import logging
from pinecone import Pinecone
from langchain_openai import OpenAIEmbeddings
from langchain_core.tools import tool

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
INDEX_NAME = "talk-assets"

try:
    pc = Pinecone(api_key=PINECONE_API_KEY)
    index = pc.Index(INDEX_NAME)
    embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
except:
    index = None

try:
    with open('conversation_rules.json', 'r', encoding='utf-8') as f:
        RULES = json.load(f)
except:
    RULES = {"mappings": {}}

# --- Legacy Function (Preserved) ---
def recommend_activities_from_user_profile(emotion: str, mobility: str) -> list:
    return [] # 실제 구현은 Tool로 대체되었으나 호환성을 위해 남김

# --- Tools for In-Context Learning Support ---
@tool
def recommend_activities_tool(user_emotion: str, mobility_status: str = "거동 가능") -> str:
    """[Tool] 사용자 감정/거동 기반 활동 추천 (RAG 적용)"""
    if not index: return "DB 연결 오류"
    
    # 규칙 기반 필터링 로직
    mappings = RULES.get("mappings", {})
    target_tags = []
    for key, tags in mappings.get("emotion_to_feeling_tags", {}).items():
        if key in user_emotion: target_tags.extend(tags)
    if not target_tags: target_tags = ["평온/이완"]

    energy_limit = 5
    for key, val in mappings.get("mobility_to_energy_range", {}).items():
        if key in mobility_status: energy_limit = val.get("max_energy", 5)

    query = f"효과: {', '.join(target_tags)}"
    vec = embeddings.embed_query(query)
    
    res = index.query(
        vector=vec, top_k=3, include_metadata=True,
        filter={"type": {"$eq": "activity"}, "ENERGY_REQUIRED": {"$lte": energy_limit}}
    )
    
    # 결과 포맷팅: LLM이 자연스럽게 제안할 수 있도록 정보 제공
    results = [f"- 활동명: {m['metadata'].get('activity_kr')} (기대효과: {m['metadata'].get('FEELING_TAGS')})" for m in res['matches']]
    return "\n".join(results) if results else "적절한 활동 없음"

@tool
def search_empathy_questions_tool(context: str) -> str:
    """
    [Tool] 대화 맥락에 맞는 공감 질문 검색.
    LLM이 '어떻게 질문해야 할지' 참고할 수 있는 가이드 질문을 제공합니다.
    """
    if not index: return "DB 연결 오류"
    vec = embeddings.embed_query(context)
    res = index.query(vector=vec, top_k=3, include_metadata=True, filter={"type": {"$eq": "question"}})
    
    # Intent를 포함하여 제공함으로써 LLM이 질문의 의도를 파악하고 변형해서 쓰도록 유도 (ICL 효과)
    questions = [f"- 질문 예시: {m['metadata'].get('question_text')} (의도: {m['metadata'].get('intent')})" for m in res['matches']]
    return "\n".join(questions) if questions else "추천 질문 없음"

TOOLS = [recommend_activities_tool, search_empathy_questions_tool]