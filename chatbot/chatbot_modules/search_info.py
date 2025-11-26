import os
import json
import logging
# import random
from typing import List

# Pinecone & LangChain
from pinecone import Pinecone
from langchain_openai import OpenAIEmbeddings
from langchain_core.tools import tool
from langchain_pinecone import PineconeVectorStore

# 지역 유사도 위한 함수.
from difflib import get_close_matches

# 연결 상태 로깅
# logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 데이터 파일 경로/ 혹시 몰라 남겨둠.
current_dir = os.path.dirname(os.path.abspath(__file__))
ordinance_file_path = os.path.join(current_dir, '../data/ordinance_region_list.json')
facilities_file_path = os.path.join(current_dir, '../data/facilities_region_list.json')

# 설정
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
INDEX_NAME = "funeral-services"
EMBEDDING_MODEL = "text-embedding-3-small"

# 전역 객체 초기화
try:
    pc = Pinecone(api_key=PINECONE_API_KEY)
    index = pc.Index(INDEX_NAME)
    embeddings = OpenAIEmbeddings(model=EMBEDDING_MODEL)
except Exception as e:
    logger.warning(f"Pinecone 초기화 실패: {e}")
    index = None

vectorstore_ordinance = PineconeVectorStore(
    index=index, 
    embedding=embeddings,
    namespace="ordinance"
)
vectorstore_funeral_facilities = PineconeVectorStore(
    index=index, 
    embedding=embeddings,
    namespace='funeral_facilities'
)
vectorstore_digital_legacy = PineconeVectorStore(
    index=index, 
    embedding=embeddings,
    namespace='digital_legacy'
)
vectorstore_legacy = PineconeVectorStore(
    index=index, 
    embedding=embeddings,
    namespace='legacy'
)

with open(ordinance_file_path, 'r', encoding='utf-8') as f:
    region_list_json = json.load(f)
    # print(region_list_json)
    
with open(facilities_file_path, 'r', encoding='utf-8') as f:
    facilities_region_list_json = json.load(f)
    # print(facilities_region_list_json)


# 유사한 지역 반환 함수
def find_matching_regions(user_input, region_list, n=3):
    """유사한 지역 여러 개 반환"""
    matched = []
    
    # 1. 양방향 체크
    for region in region_list:
        if user_input in region or region in user_input:
            matched.append(region)
            if len(matched) >= n:
                return matched
    
    # 2. 유사도 기반 매칭
    if not matched:
        matched = get_close_matches(user_input, region_list, n=n, cutoff=0.6)
    
    return matched if matched else None

@tool
def search_public_funeral_ordinance(query: str, region: str = None):
    """
    공영장례 조례를 검색합니다.
    
    Args:
        query: 검색어 (예: "지원 대상")
        region: 지역명 (예: "수원시", "서울특별시 강남구, 인천광역시 서구")
    """
    # filter_dict 먼저 초기화
    filter_dict = {"type": "Public_Funeral_Ordinance"}
    k = 3
    
    if region:
        region_list = region_list_json["public_funeral_ordinance"]
        matched = find_matching_regions(region, region_list, n=k)  # 여러 개
        # print(f"공영 장례 조례 매칭된 지역들 최대 {k}개",matched)
        if matched:
            if len(matched) == 1:
                filter_dict["region"] = matched[0]  # 1개면 직접
            else:
                filter_dict["region"] = {"$in": matched}  # 여러 개면 in

    results = vectorstore_ordinance.similarity_search(query, k=k, filter=filter_dict)
    return results

@tool
def search_cremation_subsidy_ordinance(query: str, region: str = None):
    """
    화장 장려금 조례를 검색합니다.  
    제외 대상에 대한 정보가 말이 뒤죽박죽 되어 이해하기 어려울 경우 다음의 사항을 바탕으로 이해한다.
    1.「장사 등에 관한 법률」 제7조 제2항을 위반한 경우
    2. 다른 법령에 따라 화장에 대한 지원금을 받은 경우
    
    Args:
        query: 검색어 (예: "지원 대상")
        region: 지역명 (예: "강원도 고성군", "서울 강남")
    """
    filter_dict = {"type": "Cremation_Subsidy_Ordinance"}
    k = 3
    
    if region:
        region_list = region_list_json["cremation_detail"] + region_list_json["cremation_etcetera"]
        matched = find_matching_regions(region, region_list, n=k)  # 여러 개
        # print(f"화장 장려금 조례 매칭된 지역들 최대 {k}개",matched)

        if matched:
            if len(matched) == 1:
                filter_dict["region"] = matched[0]  # 1개면 직접
            else:
                filter_dict["region"] = {"$in": matched}  # 여러 개면 in

    results = vectorstore_ordinance.similarity_search(query, k=k, filter=filter_dict)
    
    # print("툴 검색 결과:",results)
    return results

@tool
def search_funeral_facilities(query: str, region: str = None, regions : List[str] = None):
    """
    장례 시설을 검색합니다. 
    
    Args:
        query: 검색 문장 (예: "경기도 수원시 시설 좋은 묘지", "대구 남구 천주교 납골당")
        region: 지역명, 지역 한 개 검색 시 사용 (예: "경기도 성남시", "경상북도 경주시")
        regions: 지역명, 지역 여러개 검색 시 사용 (예: ["경기도 의왕시", "경기도 안양시", "경기도 군포시"], ["경상남도 양산시", "경상남도 밀양시"])

    """
    print(f"쿼리 : {query}, 지역 : {region}, 지역들 : {regions}")

    all_regions = []
    for r_list in facilities_region_list_json.values():
        all_regions.extend(r_list)
    all_regions = sorted(list(set(all_regions)))

    results_list = []
    if regions == None:
        regions = [region]
    k = 10 // len(regions)     # 비장의 코드 : 지역 많아지면 시간 느려져서 이렇게 했다. 물론 지역은 최대 3개로(프롬프트를 통해) 제한함.

    for rgn in regions:

        filter_dict = {}

        if rgn: # 하나의 지역
            matched = find_matching_regions(rgn, all_regions, n=100) 
            print(f"매칭된 지역: {matched}")

            if matched:         # 매치 없더라도 아무거나 벡터 유사도로 넘겨줄라고 else: continue 안 했다. 
                if len(matched) == 1:
                    filter_dict["region"] = matched[0]  
                else:
                    filter_dict["region"] = {"$in": matched} 

        try:
            results = vectorstore_funeral_facilities.similarity_search(
                query, 
                k=k, 
                filter=filter_dict
            )
            print(f"검색 결과 {len(results)}건 반환")
            results_list.extend(results)
            
        except Exception as e:
            print(f"검색 오류: {e}")
            continue
        
        
    unique_results = []
    seen_content = set()
    for doc in results_list:
        if doc.page_content not in seen_content:
            unique_results.append(doc)
            seen_content.add(doc.page_content)

    # print(f"최종 병합된 검색 결과: {len(unique_results)}건")
    return unique_results

@tool
def search_digital_legacy(query: str):
    """
    디지털 유산 정보를 검색합니다.
    
    Args:
        query: 검색어 (예: "카카오톡 탈퇴 시 삭제되는 데이터", "추모 프로필 주요 기능 요약")
    """
    
    
    results = vectorstore_digital_legacy.similarity_search(query, k=5)

    print("툴 검색 결과:",results)
    return results

@tool
def search_legacy(query: str):
    """
    유산과 관련된 정보를 검색합니다.  

    Args:
        query: 검색어 (예: "피상속인의 직계비속", "증여세 과세 대상")
    """
    
    results = vectorstore_legacy.similarity_search(query, k=5)

    print("툴 검색 결과:",results)
    return results

# 외부 모듈에서 import 할 수 있도록 TOOLS 리스트 정의
TOOLS_INFO = [search_public_funeral_ordinance, 
              search_cremation_subsidy_ordinance, 
              search_funeral_facilities,
              search_digital_legacy,  
              search_legacy]