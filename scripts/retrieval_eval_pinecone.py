"""
retrieval_eval_pinecone.py

- Pinecone 인덱스(digital-legacy-kb) + questions_example.json(100문항)을 사용해서
  리트리버 성능을 간단히 확인하는 스크립트.

전제:
- pip install pinecone-client python-dotenv openai numpy
- .env 또는 환경변수에 PINECONE_API_KEY 설정
"""

import os
import json
from pathlib import Path
from typing import List, Dict, Any, Set

import numpy as np
from pinecone import Pinecone
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI()

print("[DEBUG] CURRENT WORKING DIR =", os.getcwd())
# =========================================================
# 1. 설정값
# =========================================================

BASE_DIR = Path(__file__).resolve().parent.parent  # .../SKN19-3rd-3team

QUESTIONS_PATH = BASE_DIR / "data" / "questions_example" / "questions_example.json"

INDEX_NAME = "digital-legacy-kb"
NAMESPACE = None  # 네임스페이스 쓰면 문자열로 설정

# OpenAI 임베딩 모델 이름 (1536차원)
EMBEDDING_MODEL_NAME = "text-embedding-3-small"

TOP_K = 3

EXPECTED_CHUNK_IDS_BY_QUESTION_ID: Dict[str, List[str]] = {
    # 필요하면 나중에 채우기
}

# =========================================================
# 2. 유틸 함수
# =========================================================

def load_questions(path: Path) -> List[Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    # {"questions": [...]} 형태 or 바로 리스트 둘 다 지원
    if isinstance(data, dict) and "questions" in data:
        return data["questions"]
    elif isinstance(data, list):
        return data
    else:
        raise ValueError("questions_example.json 형식이 예상과 다릅니다. 'questions' 키를 확인해주세요.")

def embed_texts(texts: List[str]) -> np.ndarray:
    """
    OpenAI 임베딩 API를 사용해 텍스트 리스트를 벡터로 변환.
    text-embedding-3-small: 1536차원 임베딩 생성
    """
    res = client.embeddings.create(
        model=EMBEDDING_MODEL_NAME,
        input=texts
    )
    vectors = [d.embedding for d in res.data]
    return np.array(vectors, dtype="float32")

def preview_text(text: str, max_len: int = 80) -> str:
    """검색된 청크의 본문 일부만 잘라서 보여주는 용도."""
    text = (text or "").replace("\n", " ").strip()
    if len(text) <= max_len:
        return text
    return text[:max_len] + "..."


# =========================================================
# 3. 메인 평가 로직
# =========================================================

def main():
    # 3-1. 환경변수에서 Pinecone 키 읽기
    api_key = os.environ.get("PINECONE_API_KEY")
    if not api_key:
        raise RuntimeError("PINECONE_API_KEY 환경변수가 설정되어 있지 않습니다.")

    # 3-2. 질문 로드
    print("[DEBUG] QUESTIONS_PATH =", QUESTIONS_PATH)
    print("[DEBUG] EXISTS =", QUESTIONS_PATH.exists())

    questions: List[Dict[str, Any]] = load_questions(QUESTIONS_PATH)

    # 3-3. Pinecone & 임베딩 모델 초기화

    print(f"[INFO] Init Pinecone & embedding model")
    pc = Pinecone(api_key=api_key)
    index = pc.Index(INDEX_NAME)

    print(f"[INFO] Using OpenAI embedding model: {EMBEDDING_MODEL_NAME}")

    # 3-4. 질문별 검색 및 (옵션) Hit@K 평가

    print("[INFO] Evaluating retriever with Pinecone index...")

    total_for_eval = 0
    hit_at_k = 0

    for q in questions:
        qid = q.get("id")
        qtext = q.get("question") or q.get("question_ko")
        platform = q.get("platform")
        category = q.get("category")

        if not qid or not qtext:
            print(f"[WARN] 잘못된 질문 포맷 (id/question 없음): {q}")
            continue

        # 질문 임베딩 생성
        q_emb = embed_texts([qtext])[0]  # (1536,)

        # Pinecone에서 검색
        query_kwargs = {
            "vector": q_emb.tolist(),
            "top_k": TOP_K,
            "include_metadata": True,
        }
        if NAMESPACE:
            query_kwargs["namespace"] = NAMESPACE

        result = index.query(**query_kwargs)

        matches = result.get("matches", [])

        # -----------------------------
        # 출력
        # -----------------------------
        print("=" * 80)
        print(f"[질문 ID] {qid}")
        if platform or category:
            print(f"[플랫폼/카테고리] {platform} / {category}")
        print(f"[질문] {qtext}")
        print(f"[Top-{TOP_K} 결과] (청크 ID, score, platform, source_id, 미리보기)")

        retrieved_ids: Set[str] = set()

        for rank, m in enumerate(matches, start=1):
            cid = m["id"]
            score = float(m["score"])
            meta = m.get("metadata", {}) or {}
            src_platform = meta.get("platform")
            source_id = meta.get("source_id") or meta.get("title")
            text_preview = preview_text(meta.get("text", ""))

            retrieved_ids.add(cid)

            print(
                f"  {rank}. {cid}  "
                f"(score={score:.4f}, platform={src_platform}, source_id={source_id})"
            )
            print(f"      ▶ {text_preview}")

        # -----------------------------
        # Hit@K 계산 (정답 매핑이 있는 경우에만)
        # -----------------------------
        if qid in EXPECTED_CHUNK_IDS_BY_QUESTION_ID:
            total_for_eval += 1
            expected_set = set(EXPECTED_CHUNK_IDS_BY_QUESTION_ID[qid])
            is_hit = bool(expected_set & retrieved_ids)
            print(f"[기대 청크] {expected_set}")
            print(f"[Hit@{TOP_K}] {is_hit}")
            if is_hit:
                hit_at_k += 1
        else:
            print("[참고] 이 질문은 EXPECTED_CHUNK_IDS_BY_QUESTION_ID에 정답이 지정되어 있지 않습니다.")

    # -----------------------------
    # 3-5. 전체 Hit@K 요약
    # -----------------------------
    if total_for_eval > 0:
        hit_rate = hit_at_k / total_for_eval
        print("=" * 80)
        print(f"[요약] 평가 대상 질문 수: {total_for_eval}")
        print(f"[요약] Hit@{TOP_K}: {hit_at_k} / {total_for_eval} = {hit_rate:.2f}")
    else:
        print("[INFO] EXPECTED_CHUNK_IDS_BY_QUESTION_ID가 비어 있어 Hit Rate를 계산하지 않았습니다.")


if __name__ == "__main__":
    main()
