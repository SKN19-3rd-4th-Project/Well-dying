"""
identity_verification_retrieval_eval.py

- 청킹된 JSON(청크) + 질문 JSON(30문항)을 사용해서
  간단한 리트리버 평가를 수행하는 스크립트.

전제:
- pip install sentence-transformers
"""

import json
from pathlib import Path
from typing import List, Dict, Any, Tuple

import numpy as np
from sentence_transformers import SentenceTransformer


# =========================================================
# 1. 설정값
# =========================================================

CHUNKS_PATH = Path("./data/digital_asset_management_chunked_data/Identity_verification_service_chunked.json")
QUESTIONS_PATH = Path("./data/digital_asset_management_questions/Identity_verification_service_questions.json")

# sentence-transformers 모델 이름
# 실제 프로젝트에서 사용할 임베딩 모델과 동일하게 맞춰주는 것이 좋다.
EMBEDDING_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

TOP_K = 3  # top-k 검색 개수


# (옵션) 질문별 기대 청크 ID 정답 세트
#  - 여러 청크가 정답일 수 있으므로 리스트로 둔다.
#  - 필요 없으면 빈 dict로 두고, Hit Rate 계산 부분을 건너뛰어도 된다.
EXPECTED_CHUNK_IDS_BY_QUESTION_ID: Dict[str, List[str]] = {
    # Overview & 용어는 대부분 overview_chunk_1에서 커버됨
    "Q001": ["identity_verification_overview_chunk_1"],
    "Q002": ["identity_verification_overview_chunk_1"],
    "Q003": ["identity_verification_overview_chunk_1"],
    "Q004": ["identity_verification_overview_chunk_1"],
    "Q005": ["identity_verification_overview_chunk_1"],
    "Q006": ["identity_verification_overview_chunk_1"],
    "Q007": ["identity_verification_overview_chunk_1"],
    "Q008": ["identity_verification_overview_chunk_1"],
    "Q009": [
        "identity_verification_overview_chunk_1",
        "identity_verification_step_02_chunk_1",
    ],
    "Q010": ["identity_verification_overview_chunk_1"],
    "Q011": ["identity_verification_overview_chunk_1"],
    "Q012": ["identity_verification_overview_chunk_1"],
    "Q013": ["identity_verification_overview_chunk_1"],
    "Q014": [
        "identity_verification_overview_chunk_2",
        "identity_verification_step_02_chunk_1",
    ],
    "Q015": [
        "identity_verification_overview_chunk_1",
        "identity_verification_step_02_chunk_1",
    ],
    # STEP 01
    "Q016": ["identity_verification_step_01_chunk_1"],
    "Q017": ["identity_verification_step_01_chunk_1"],
    "Q018": ["identity_verification_step_01_chunk_1"],
    "Q019": ["identity_verification_step_01_chunk_1"],
    "Q020": ["identity_verification_step_01_chunk_1"],
    # STEP 02
    "Q021": ["identity_verification_step_02_chunk_1"],
    "Q022": ["identity_verification_step_02_chunk_1"],
    "Q023": ["identity_verification_step_02_chunk_1"],
    "Q024": ["identity_verification_step_02_chunk_1"],
    "Q025": ["identity_verification_step_02_chunk_1"],
    # STEP 03
    "Q026": ["identity_verification_step_03_chunk_1"],
    "Q027": ["identity_verification_step_03_chunk_1"],
    "Q028": ["identity_verification_step_03_chunk_1"],
    "Q029": ["identity_verification_step_03_chunk_1"],
    "Q030": ["identity_verification_step_03_chunk_1"],
}


# =========================================================
# 2. 유틸 함수
# =========================================================

def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def cosine_sim_matrix(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """
    a: (N, D)
    b: (M, D)
    return: (N, M) 코사인 유사도 행렬

    "코사인 유사도"(두 벡터의 각도를 이용해 얼마나 비슷한 방향인지 측정하는 지표)
    """
    a_norm = a / np.linalg.norm(a, axis=1, keepdims=True)
    b_norm = b / np.linalg.norm(b, axis=1, keepdims=True)
    return np.dot(a_norm, b_norm.T)


# =========================================================
# 3. 메인 평가 로직
# =========================================================

def main():
    # -----------------------------
    # 3-1. 데이터 로드
    # -----------------------------
    chunks: List[Dict[str, Any]] = load_json(CHUNKS_PATH)
    questions: List[Dict[str, Any]] = load_json(QUESTIONS_PATH)

    chunk_ids = [c["id"] for c in chunks]
    chunk_texts = [c["text"] for c in chunks]

    # -----------------------------
    # 3-2. 임베딩 모델 로드
    # -----------------------------
    print(f"[INFO] Loading embedding model: {EMBEDDING_MODEL_NAME}")
    model = SentenceTransformer(EMBEDDING_MODEL_NAME)

    # -----------------------------
    # 3-3. 청크 임베딩 계산
    # -----------------------------
    print("[INFO] Encoding chunks...")
    chunk_embs = model.encode(
        chunk_texts,
        convert_to_numpy=True,
        show_progress_bar=True
    )  # shape: (num_chunks, dim)

    # -----------------------------
    # 3-4. 질문별 검색 및 평가
    # -----------------------------
    print("[INFO] Evaluating retriever...")

    total = 0
    hit_at_k = 0

    for q in questions:
        qid = q["id"]
        qtext = q["question_ko"]

        # 질문 임베딩
        q_emb = model.encode([qtext], convert_to_numpy=True)[0]  # (dim,)

        # 유사도 계산
        sims = cosine_sim_matrix(q_emb[None, :], chunk_embs)[0]  # (num_chunks,)
        top_idx = np.argsort(sims)[::-1][:TOP_K]

        retrieved = [
            (chunk_ids[i], float(sims[i]))
            for i in top_idx
        ]

        print("=" * 80)
        print(f"[질문 ID] {qid}")
        print(f"[질문] {qtext}")
        print(f"[Top-{TOP_K} 결과] (청크 ID, 유사도)")
        for rank, (cid, score) in enumerate(retrieved, start=1):
            print(f"  {rank}. {cid}  (score={score:.4f})")

        # 정답 세트가 정의되어 있다면 Hit@K 계산
        if qid in EXPECTED_CHUNK_IDS_BY_QUESTION_ID:
            total += 1
            expected_set = set(EXPECTED_CHUNK_IDS_BY_QUESTION_ID[qid])
            retrieved_ids = {cid for cid, _ in retrieved}
            is_hit = bool(expected_set & retrieved_ids)
            print(f"[기대 청크] {expected_set}")
            print(f"[Hit@{TOP_K}] {is_hit}")
            if is_hit:
                hit_at_k += 1
        else:
            print("[주의] 이 질문은 EXPECTED_CHUNK_IDS_BY_QUESTION_ID에 정답이 지정되어 있지 않습니다.")

    if total > 0:
        hit_rate = hit_at_k / total
        print("=" * 80)
        print(f"[요약] 평가 대상 질문 수: {total}")
        print(f"[요약] Hit@{TOP_K}: {hit_at_k} / {total} = {hit_rate:.2f}")
    else:
        print("[INFO] EXPECTED_CHUNK_IDS_BY_QUESTION_ID에 정답이 설정된 질문이 없어 Hit Rate를 계산하지 않았습니다.")


if __name__ == "__main__":
    main()
