import os
import json
from typing import List

from dotenv import load_dotenv
from openai import OpenAI
from pinecone import Pinecone, ServerlessSpec

# .env 파일 로드
load_dotenv()

# =========================
# 1. 기본 설정
# =========================
INDEX_NAME = "digital-legacy-kb"  # 원하는 이름으로 수정 가능
EMBED_MODEL = "text-embedding-3-small"   # OpenAI 임베딩 모델 이름
EMBED_DIM = 1536                         # text-embedding-3-small의 차원 수

# 환경 변수에서 API 키 읽기
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")

if OPENAI_API_KEY is None:
    raise RuntimeError("OPENAI_API_KEY 환경 변수가 설정되어 있지 않습니다.")

if PINECONE_API_KEY is None:
    raise RuntimeError("PINECONE_API_KEY 환경 변수가 설정되어 있지 않습니다.")

# 클라이언트 생성
client = OpenAI()  # 환경 변수의 OPENAI_API_KEY를 자동 사용
pc = Pinecone(api_key=PINECONE_API_KEY)


# =========================
# 2. 인덱스 생성 (최초 1회)
# =========================
existing_indexes = [idx["name"] for idx in pc.list_indexes()]
if INDEX_NAME not in existing_indexes:
    print(f"[INFO] 인덱스가 없어 새로 생성합니다: {INDEX_NAME}")
    pc.create_index(
        name=INDEX_NAME,
        dimension=EMBED_DIM,
        metric="cosine",  # 코사인 유사도
        spec=ServerlessSpec(cloud="aws", region="us-east-1"),
    )
else:
    print(f"[INFO] 이미 존재하는 인덱스입니다: {INDEX_NAME}")

index = pc.Index(INDEX_NAME)


# =========================
# 3. 임베딩 함수 (배치 버전)
# =========================
def embed_texts(texts: List[str]) -> List[List[float]]:
    """
    여러 개의 텍스트를 한 번에 임베딩하는 함수.
    """
    resp = client.embeddings.create(
        model=EMBED_MODEL,
        input=texts,
    )
    # resp.data[i].embedding 형태로 벡터 접근
    return [d.embedding for d in resp.data]


# =========================
# 4. 청크 JSON 로드
# =========================
def load_chunks(path: str):
    with open(path, "r", encoding="utf-8") as f:
        chunks = json.load(f)
    print(f"[INFO] 총 {len(chunks)}개의 청크 로드 완료.")
    return chunks


# =========================
# 5. Pinecone로 업로드 (업서트)
# =========================
def upsert_chunks_to_pinecone(chunks, batch_size: int = 100):
    total = len(chunks)
    for start in range(0, total, batch_size):
        end = min(start + batch_size, total)
        batch = chunks[start:end]

        # 1) 텍스트 / ID 추출
        texts = [c["text"] for c in batch]   # JSON의 text 필드
        ids = [c["id"] for c in batch]       # JSON의 id 필드

        # 2) 메타데이터 구성
        metadatas = []
        for c in batch:
            base_meta = c.get("metadata", {}) or {}
        
            # 기본 메타데이터 + 원본 metadata 합치기
            meta = {
                "source": "online_shoppingmal_chunked",   # ← 여기도 바뀌어야 함(플랫폼 이름)
                "chunk_id": c["id"],
                "text": c["text"],
            }
            meta.update(base_meta)
        
            # 🔥 None 제거
            clean_meta = {k: v for k, v in meta.items() if v is not None}
        
            metadatas.append(clean_meta)

        # 3) 임베딩 생성
        embeddings = embed_texts(texts)

        # 4) Pinecone 벡터 구성
        vectors = []
        for cid, emb, meta in zip(ids, embeddings, metadatas):
            vectors.append({
                "id": cid,
                "values": emb,
                "metadata": meta,
            })

        # 5) 업서트(upsert)(용어: 있으면 갱신, 없으면 삽입)
        index.upsert(vectors=vectors)
        print(f"[INFO] 업서트 진행: {end}/{total} 개 완료.")

if __name__ == "__main__":
    # JSON 파일 경로 (프로젝트 구조에 맞게 수정)
    json_path = os.path.join(
        os.path.dirname(__file__),
        "..",
        "data",
        "digital_asset_management_chunked_data",        # ← 플랫폼별 폴더 이름
        "online_shoppingmal_chunked.json",       # ← 업로드하려는 JSON 파일 이름
    )

    print(f"[INFO] 청크 파일 경로: {json_path}")
    chunks = load_chunks(json_path)
    upsert_chunks_to_pinecone(chunks, batch_size=100)
    print("[INFO] 모든 청크 업로드 완료.")

    stats = index.describe_index_stats()
    print("[INFO] 인덱스 통계:")
    print(stats)