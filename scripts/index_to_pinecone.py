import os
import json
import time
from pathlib import Path
from dotenv import load_dotenv
from pinecone import Pinecone, ServerlessSpec
from openai import OpenAI

# 환경 변수 로드
load_dotenv()

# 설정
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
INDEX_NAME = "temp"
NAMESPACE = "well-dying"
PROCESSED_DIR = "data/processed"
DATA_FILE = "unified_well_dying_data.jsonl"

# 클라이언트 초기화
pc = Pinecone(api_key=PINECONE_API_KEY)
openai_client = OpenAI(api_key=OPENAI_API_KEY)

def get_embedding(text: str, model: str = "text-embedding-3-small") -> list:
    """텍스트를 임베딩 벡터로 변환"""
    try:
        response = openai_client.embeddings.create(
            model=model,
            input=text
        )
        return response.data[0].embedding
    except Exception as e:
        print(f"임베딩 생성 오류: {e}")
        raise

def setup_index():
    """Pinecone 인덱스 확인"""
    existing_indexes = [index.name for index in pc.list_indexes()]
    
    if INDEX_NAME not in existing_indexes:
        print(f"오류: 인덱스 '{INDEX_NAME}'가 존재하지 않습니다.")
        return None
    
    print(f"기존 인덱스 '{INDEX_NAME}' 사용 (Namespace: {NAMESPACE})")
    return pc.Index(INDEX_NAME)

def index_data():
    """데이터 인덱싱"""
    index = setup_index()
    file_path = Path(PROCESSED_DIR) / DATA_FILE
    
    if not file_path.exists():
        print(f"오류: 데이터 파일이 없습니다 - {file_path}")
        return

    print(f"데이터 파일 읽기: {file_path}")
    
    vectors = []
    batch_size = 100
    count = 0
    
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        total_lines = len(lines)
        print(f"총 {total_lines}개 데이터 처리 시작")
        
        for i, line in enumerate(lines):
            if not line.strip():
                continue
                
            data = json.loads(line)
            
            # 데이터 추출
            context = data.get('context', '')
            instruction = data.get('instruction', '')
            meta = data.get('metadata', {})
            
            # 텍스트 구성
            text = f"주제: {instruction}\n내용: {context}"
            
            # ID 생성
            doc_id = f"{meta.get('category', 'unknown')}_{i}"
            
            # 메타데이터 구성 (Pinecone은 메타데이터 크기 제한이 있으므로 필수적인 것만)
            metadata = {
                'text': text, # 검색 결과로 텍스트를 반환하기 위해 저장
                'title': instruction,
                'source': meta.get('source_file', 'unknown'),
                'category': meta.get('category', 'unknown')
            }
            
            # 임베딩 생성
            try:
                embedding = get_embedding(text)
                vectors.append({
                    "id": doc_id,
                    "values": embedding,
                    "metadata": metadata
                })
            except Exception as e:
                print(f"데이터 처리 중 오류 (ID: {doc_id}): {e}")
                continue
            
            # 배치 업로드
            if len(vectors) >= batch_size:
                try:
                    index.upsert(vectors=vectors, namespace=NAMESPACE)
                    count += len(vectors)
                    print(f"진행률: {count}/{total_lines} ({(count/total_lines)*100:.1f}%)")
                    vectors = []
                    time.sleep(0.5) # Rate limit 조절
                except Exception as e:
                    print(f"배치 업로드 오류: {e}")
        
        # 남은 벡터 업로드
        if vectors:
            try:
                index.upsert(vectors=vectors, namespace=NAMESPACE)
                count += len(vectors)
                print(f"최종 완료: {count}/{total_lines}")
            except Exception as e:
                print(f"마지막 배치 업로드 오류: {e}")

if __name__ == "__main__":
    index_data()
