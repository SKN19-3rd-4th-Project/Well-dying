import os
import json
import logging
import random

# Pinecone & LangChain
from pinecone import Pinecone
from langchain_openai import OpenAIEmbeddings
from langchain_core.tools import tool

# 연결 상태 로깅
# logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 데이터 파일 경로
current_dir = os.path.dirname(os.path.abspath(__file__))
file_path = os.path.join(current_dir, '../data/conversation_rules.json')

# 설정
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
INDEX_NAME = "talk-assets"
EMBEDDING_MODEL = "text-embedding-3-small"

# 전역 객체 초기화
try:
    pc = Pinecone(api_key=PINECONE_API_KEY)
    index = pc.Index(INDEX_NAME)
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
    if not index: return "DB 연결 오류"

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
    if not index: return "DB 연결 오류"
    
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

# 외부 모듈에서 import 할 수 있도록 TOOLS 리스트 정의
TOOLS_TALK = [recommend_activities_tool, search_empathy_questions_tool]