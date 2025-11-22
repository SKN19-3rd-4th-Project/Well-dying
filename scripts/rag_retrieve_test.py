import os
from openai import OpenAI
from pinecone import Pinecone

# =====================================
# 1. .env 읽기
# =====================================
from dotenv import load_dotenv
load_dotenv()

# =====================================
# 2. 클라이언트 준비
# =====================================
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")

if OPENAI_API_KEY is None or PINECONE_API_KEY is None:
    raise RuntimeError("환경변수 OPENAI_API_KEY 또는 PINECONE_API_KEY가 설정되지 않았습니다.")

client = OpenAI()
pc = Pinecone(api_key=PINECONE_API_KEY)

INDEX_NAME = "identity-verification-kb"
index = pc.Index(INDEX_NAME)

EMBED_MODEL = "text-embedding-3-small"


# =====================================
# 3. 임베딩 함수
# =====================================
def embed(text: str):
    """
    어디에서: 이 파일 내부에서 사용.
    무엇을: 문자열(text)을 벡터(embedding)로 변환.
    어떻게: OpenAI 임베딩 모델 text-embedding-3-small 사용.
    """
    resp = client.embeddings.create(
        model=EMBED_MODEL,
        input=text
    )
    return resp.data[0].embedding


# =====================================
# 4. 리트리버 함수
# =====================================
def retrieve(query: str, top_k: int = 3):
    """
    어디에서: RAG 검색 단계에서 첫 번째로 호출되는 함수.
    무엇을: 질문(query)과 가장 유사한 Top-K 문서 청크를 Pinecone에서 검색.
    어떻게:
        1. 질문 임베딩 생성
        2. Pinecone index.query() 호출
        3. id, score, metadata(text 등) 포함하여 반환
    """
    q_vec = embed(query)

    result = index.query(
        vector=q_vec,
        top_k=top_k,
        include_metadata=True
    )

    return result["matches"]


# =====================================
# 5. 간단 테스트
# =====================================
if __name__ == "__main__":
    test_query = "본인확인 내역 조회 서비스는 어떤 목적을 가지고 있나요?"

    print("\n[TEST] 리트리버 실행")
    print("[질문]:", test_query)
    print("--------------------------------------------------")

    matches = retrieve(test_query, top_k=3)

    for i, m in enumerate(matches, 1):
        print(f"[Top {i}]")
        print("  chunk_id:", m["id"])
        print("  score   :", m["score"])
        print("  text    :", m["metadata"].get("text")[:120], "...")  # 앞 120자만
        print()
