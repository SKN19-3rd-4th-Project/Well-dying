# interactive_qa.py

import os
from typing import Dict, Any, List

from dotenv import load_dotenv          # "dotenv"(환경변수를 .env 파일에서 읽어주는 라이브러리)
from pinecone import Pinecone           # "Pinecone 클라이언트"(벡터DB에 연결하는 객체)
from openai import OpenAI               # "OpenAI 클라이언트"(LLM/임베딩 호출하는 객체)

# =========================
# 1. 환경 설정 & 클라이언트 준비
# =========================

load_dotenv()  # .env 파일 내용 읽어오기

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")

if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY가 .env에 없습니다.")
if not PINECONE_API_KEY:
    raise RuntimeError("PINECONE_API_KEY가 .env에 없습니다.")

# 네가 사용 중인 인덱스 이름 (기억하고 있는 건 digital-legacy-kb)
INDEX_NAME = "digital-legacy-kb"
# namespace를 따로 안 썼으면 "" 또는 None으로 두면 됨
NAMESPACE = ""  # 필요하면 "naver", "kakao" 같은 namespace 이름으로 변경

# 클라이언트 생성
pc = Pinecone(api_key=PINECONE_API_KEY)
index = pc.Index(INDEX_NAME)

client = OpenAI(api_key=OPENAI_API_KEY)

EMBED_MODEL = "text-embedding-3-small"  # "임베딩 모델"(문장을 벡터로 바꾸는 모델)
CHAT_MODEL = "gpt-4o-mini"              # "챗 모델"(실제 답변을 만들어주는 LLM)


# =========================
# 2. 질문 1개를 처리하는 함수
# =========================
def detect_scenario(question: str) -> str | None:
    """
    사용자의 질문을 보고
    - '사후 유족 처리'
    - '생전 계정 정리'
    둘 중 어디에 더 가까운지 간단히 분류한다.
    해당 안 되면 None 반환.
    """

    q = question.strip()

    # 1) 사후/유족 관련 키워드 우선 체크
    death_keywords = [
        "사망", "돌아가신", "유족", "상속", "사후", "망자", "고인",
        "사망자 계정", "사망한 회원", "사망한 사람", "사망한 가족"
    ]
    if any(kw in q for kw in death_keywords):
        return "사후 유족 처리"

    # 2) 생전 탈퇴/정리 관련 키워드
    living_keywords = [
        "회원 탈퇴", "아이디 탈퇴", "계정 탈퇴", "계정 정리",
        "재가입", "가입 해지", "탈퇴하고 싶", "가입 취소"
    ]
    if any(kw in q for kw in living_keywords):
        return "생전 계정 정리"

    # 3) 둘 다 아니면 필터 없이 검색
    return None

def retrieve_and_answer(question: str, top_k: int = 3) -> Dict[str, Any]:
    # 0) 시나리오 먼저 감지
    scenario = detect_scenario(question)

    emb_response = client.embeddings.create(
        model=EMBED_MODEL,
        input=question
    )
    embedding = emb_response.data[0].embedding

    # 1) 기본 필터 구성
    pinecone_filter: dict = {}

    # 네이버 관련 질문에만 시나리오 필터를 걸고 싶으면
    # 여기서 question 내용 보고 'naver' 여부를 판단해서 조건 추가해도 됨.
    if scenario is not None:
        pinecone_filter["scenario"] = scenario

    # 2) Pinecone 쿼리 호출 (필터가 없으면 None 전달)
    query_result = index.query(
        vector=embedding,
        top_k=top_k,
        include_metadata=True,
        namespace=NAMESPACE if NAMESPACE else None,
        filter=pinecone_filter or None,
    )

    matches = query_result.matches

    # 2-3. 검색 결과에서 context 문자열 만들기
    context_parts = []
    for m in matches:
        # 메타데이터에 어떤 키로 내용이 들어갔는지에 따라 수정:
        # 예: "content", "text", "chunk_text" 등
        meta = m.metadata or {}
        content = (
            meta.get("content")
            or meta.get("text")
            or meta.get("chunk_text")
            or ""
        )
        chunk_id = m.id
        context_parts.append(f"[{chunk_id}] {content}")

    context = "\n\n".join(context_parts)

    # 2-4. LLM에 보낼 프롬프트 구성
    system_prompt = ('''
        "너는 디지털 유산(온라인 계정, 디지털 자산, 추모 서비스 등)에 대해 "
        "공식 문서와 정책을 기반으로 답변하는 도움 챗봇이야. "
        "아래 '참고 문서' 내용만 활용해서 사용자의 질문에 한국어로 답해줘. "
        "문서에 정보가 없으면, 추측하지 말고 모른다고 말해줘."
        당신은 시한부 환자, 마음이 힘든 분, 노년층을 지원하는
        '따뜻한 호스피스 동반자'이자 '심리 상담사'입니다.

        [핵심 원칙]
        - 사용자의 감정을 얕게 판단하지 말고, 그 감정의 '무게'를 존중하세요.
        - 해결책을 강요하지 말고, 그저 곁에서 들어주는 사람처럼 이야기하세요.
        - 사용자의 표현을 그대로 복붙하거나 분석하지 마세요.
          (예: "~라고 하셨군요", "~을 느끼고 계시는군요" 금지)

        [말투]
        - 항상 끝이 "~요", "~세요"로 끝나는 **존댓말**만 사용하세요.
        - 반말, 반존대 금지: "힘들겠구나", "어떤 이야기를 나누고 싶어?" 같은 표현은 절대 쓰지 마세요.
        - "~~라고 느끼고 계시는군요"처럼 분석하는 톤은 피하고,
          "많이 힘드셨겠어요", "혼자 버티느라 애쓰셨죠"처럼 사람 냄새 나는 표현을 사용하세요.

        [응답 구조]
        1) 사용자의 감정을 부드럽게 감싸주는 한 문장
        2) 필요하면 조심스러운 질문 0~1문장 (없어도 됨)
        3) 전체 2~3문장, 짧고 안정적인 길이

        [금지 예시]
        - "그런 마음이 드는 건 정말 힘들겠구나." (X, 반말)
        - "지금 ~~라고 느끼고 계시는군요." (X, 분석체)
        - "꼭 ~~해보세요." (X, 숙제/권유)
        """

        ACTIVITY_SYSTEM_PROMPT = """
        당신은 마음이 지친 분에게 작은 환기활동을 제안하는 호스피스 케어기버입니다.

        [원칙]
        - '혹시 괜찮으시다면', '부담 없으시다면'처럼 제안은 항상 가볍고 부드럽게.
        - '꼭 해보세요', '반드시 좋습니다' 같은 강한 권유 표현은 쓰지 마세요.
        - 활동은 예시로 1~2개만, 간접적으로 제안하세요.
        - 전체 3~4문장, 조용하고 따뜻한 톤을 유지하세요.
        """

        CHOICE_SYSTEM_PROMPT = """
        당신은 호스피스 케어기버입니다.
        대화 중간에, '활동 찾기'와 '계속 이야기하기' 중 하나를 선택하도록 아주 조심스럽게 제안하려 합니다.

        [작성 지침]
        1. 내담자의 마지막 말("{user_message}")에 대해 먼저 부드럽게 공감해 주세요.
        2. 그 후, "혹시 괜찮으시다면...", "부담 없으시다면..." 처럼 아주 부드러운 톤으로 활동 찾기를 제안하세요.
        3. "지금처럼 이야기를 이어가도 괜찮다"는 여지를 반드시 남기세요.
        4. 전체 2~3문장.
    '''
    )

    user_prompt = (
        f"질문: {question}\n\n"
        f"참고 문서:\n{context}"
    )

    completion = client.chat.completions.create(
        model=CHAT_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.2,  # "temperature"(출력 다양성 정도; 낮을수록 일관된 답변)
    )

    answer = completion.choices[0].message.content.strip()

    return {
        "question": question,
        "matches": matches,
        "context": context,
        "answer": answer,
    }


# =========================
# 3. 터미널에서 질문을 받는 메인 루프
# =========================

def main():
    print("=== 디지털 유산 QA 인터랙티브 테스트 ===")
    print("질문을 입력하면 Pinecone 검색 + LLM 응답을 확인합니다.")
    print("종료하려면 exit / quit / q 를 입력하세요.\n")

    while True:  # "while 루프"(조건이 참인 동안 계속 반복하는 문장)
        q = input("Q> ").strip()

        # 종료 명령
        if q.lower() in ("exit", "quit", "q"):
            print("테스트를 종료합니다.")
            break

        # 빈 입력은 무시
        if not q:
            continue

        try:
            result = retrieve_and_answer(q)
        except Exception as e:
            print("[에러 발생]", e)
            continue

        print("\n[질문]")
        print(result["question"])

        print("\n[리트리버 상위 문서 목록]")
        for i, m in enumerate(result["matches"], start=1):
            chunk_id = m.id
            score = getattr(m, "score", None)
            print(f"  {i}. {chunk_id} (score={score})")

        print("\n[모델 응답]")
        print(result["answer"])
        print("-" * 60 + "\n")


if __name__ == "__main__":
    # 이 파일을 직접 실행했을 때만 main()을 돌리라는 의미
    main()
