import os
import json
import logging
from pathlib import Path
from collections import defaultdict, Counter
from typing import Dict, Set

from langchain_openai import OpenAIEmbeddings
from langchain_core.tools import tool
from pinecone import Pinecone

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
INDEX_NAME = os.getenv("PINECONE_INDEX", "talk-assets")
EMBEDDING_MODEL = os.getenv("PINECONE_EMBED_MODEL", "text-embedding-3-small")
PINECONE_HOST = os.getenv("PINECONE_HOST")  # 콘솔 새버전에서 제공되는 host 사용 시

# ---------------------------------------------------------------------------
# Load conversation rules (with fallbacks)
# ---------------------------------------------------------------------------
RULES = {}
RULE_CANDIDATES = [
    Path(__file__).resolve().parent / "data" / "conversation_rules.json",
    Path(__file__).resolve().parent / "../data/processed/conversation_rules.json",
    Path(__file__).resolve().parent / "../data/conversation_rules.json",
]
for candidate in RULE_CANDIDATES:
    try:
        if candidate.exists():
            with open(candidate, "r", encoding="utf-8") as f:
                RULES = json.load(f)
                logger.info(f"conversation_rules.json loaded from {candidate}")
                break
    except Exception as e:
        logger.warning(f"conversation_rules.json load failed at {candidate}: {e}")
if not RULES:
    logger.warning("conversation_rules.json을 찾지 못했습니다. 기본 매핑 없이 진행합니다.")

# ---------------------------------------------------------------------------
# Pinecone / Embeddings (lazy init)
# ---------------------------------------------------------------------------
pc = None
index = None
embeddings = None
_pinecone_init_attempted = False

# user-level dedup caches
_recommended_activities_by_user: Dict[str, Set[str]] = defaultdict(set)
_asked_questions_by_user: Dict[str, Set[str]] = defaultdict(set)


def _ensure_clients():
    """Initialize Pinecone/embeddings lazily to avoid import-time failures."""
    global pc, index, embeddings, _pinecone_init_attempted
    if _pinecone_init_attempted:
        return
    _pinecone_init_attempted = True

    if not PINECONE_API_KEY:
        logger.warning("Pinecone 비활성화: PINECONE_API_KEY 미설정")
        return

    try:
        pc = Pinecone(api_key=PINECONE_API_KEY)
        if PINECONE_HOST:
            index_host = PINECONE_HOST
            index = pc.Index(host=index_host)
        else:
            index = pc.Index(INDEX_NAME)
        embeddings = OpenAIEmbeddings(
            model=EMBEDDING_MODEL,
            openai_api_key=os.getenv("OPENAI_API_KEY"),
        )
        logger.info("Pinecone/Embeddings 초기화 완료")
    except Exception as e:
        logger.warning(f"Pinecone 초기화 실패: {e}")
        pc = None
        index = None
        embeddings = None


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------
@tool
def recommend_activities_tool(
    user_emotion: str,
    mobility_status: str = "거동 가능",
    user_id: str = "",
) -> str:
    """
    사용자의 감정(B1)과 거동/활동 범위(A2/A4)를 기반으로 '의미 있는 활동'을 추천합니다.
    동일 활동을 반복 추천하지 않습니다.
    """
    _ensure_clients()
    if not index or not embeddings:
        return "DB 연결 오류"

    mappings = RULES.get("mappings", {})

    target_tags = []
    for key, tags in mappings.get("emotion_to_feeling_tags", {}).items():
        if key in user_emotion:
            target_tags.extend(tags)
    if not target_tags:
        target_tags = ["평온/이완"]

    energy_limit = 5
    for key, val in mappings.get("mobility_to_energy_range", {}).items():
        if key in mobility_status:
            energy_limit = val.get("max_energy", 5)

    query = f"효과: {', '.join(target_tags)} 인 활동"
    vec = embeddings.embed_query(query)

    res = index.query(
        vector=vec,
        top_k=8,
        include_metadata=True,
        filter={"type": {"$eq": "activity"}, "ENERGY_REQUIRED": {"$lte": energy_limit}},
    )

    uid = user_id or "__global__"
    already = _recommended_activities_by_user[uid]
    seen_local: Set[str] = set()
    results = []

    for match in res.get("matches", []):
        meta = match.get("metadata", {})
        activity = meta.get("activity_kr") or meta.get("activity") or ""
        if not activity or activity in already or activity in seen_local:
            continue
        seen_local.add(activity)
        results.append(f"- {activity} (기대효과: {meta.get('FEELING_TAGS')})")
        if len(results) >= 3:
            break

    if not results:
        return "이미 추천드린 활동과 겹쳐서 새로운 추천을 찾지 못했습니다. 다른 감정이나 상황을 알려주시면 새로 찾아볼게요."

    already.update(seen_local)
    return "\n".join(results)


@tool
def search_empathy_questions_tool(
    context: str,
    depth: int = 1,
    user_id: str = "",
    recent_messages: list[str] | None = None,
) -> str:
    """
    대화 맥락에 맞는 '공감 질문'을 검색합니다.
    depth(1~3)가 커질수록 더 깊은 질문을 시도하며, 이미 질문한 내용은 피합니다.
    최근 대화 5개에서 핵심 키워드를 뽑아 쿼리에 가중치로 사용합니다.
    """
    _ensure_clients()
    if not index or not embeddings:
        return "DB 연결 오류"

    depth = max(1, min(depth, 3))

    # 최근 대화에서 상위 키워드 추출: 자주 언급 + 최근 발화 가중치
    keywords = []
    if recent_messages:
        stop = {
            "그리고",
            "그래서",
            "합니다",
            "했습니다",
            "그런데",
            "지금",
            "조금",
            "정말",
            "뭔가",
            "나는",
            "제가",
            "저는",
            "근데",
            "그러면",
        }
        weights = list(range(1, len(recent_messages[-5:]) + 1))  # 최근 발화일수록 가중치 큼
        counts: Counter[str] = Counter()
        for weight, msg in zip(weights, recent_messages[-5:]):
            for raw in msg.replace("\n", " ").split(" "):
                token = raw.strip().strip(",.?!\"'()[]")
                if len(token) < 2 or token in stop or any(c.isdigit() for c in token):
                    continue
                counts[token] += weight
        keywords = [w for w, _ in counts.most_common(5)]

    query_text = context
    if keywords:
        query_text += " / 키워드: " + ", ".join(keywords)

    vec = embeddings.embed_query(query_text)
    res = index.query(
        vector=vec,
        top_k=3 + depth,
        include_metadata=True,
        filter={"type": {"$eq": "question"}},
    )

    uid = user_id or "__global__"
    already = _asked_questions_by_user[uid]
    seen_local: Set[str] = set()

    questions = []

    for m in res.get("matches", []):
        meta = m.get("metadata", {})
        q_text = meta.get("question_text")
        if not q_text or q_text in already or q_text in seen_local:
            continue
        seen_local.add(q_text)
        questions.append(f"- {q_text} (의도: {meta.get('intent')})")
        if len(questions) >= 3:
            break

    if not questions and res.get("matches"):
        # fallback: allow repeats if nothing fresh
        questions = [
            f"- {m['metadata'].get('question_text')} (의도: {m['metadata'].get('intent')})"
            for m in res.get("matches", [])[:3]
        ]

    already.update(seen_local)
    return "\n".join(questions) if questions else "적절한 질문이 없습니다."


# Expose tool list
TOOLS = [recommend_activities_tool, search_empathy_questions_tool]
