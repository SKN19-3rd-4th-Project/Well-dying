
import pandas as pd
import json
from datetime import datetime, timedelta
from pathlib import Path
from llm_client import generate_text
import random


SIMPLE_PROMPT = """친구처럼 조용히 이야기를 들어주는 역할입니다.

규칙:
1. 사용자가 방금 한 말을 한 번 언급해 주세요.
2. 공감하는 내용 1문장만 쓰세요.
3. 건조한 말("그렇군요", "좋으시겠네요") 금지.
4. 출력에는 따옴표(" "), 화살표(→), 예시 형식을 사용하지 마세요.
5. 아래 예시는 느낌만 참고하고, 그대로 따라 쓰지 마세요.

예시(참고용):
사용자: "바빴어"
→ 요즘 많이 바쁘셨겠어요.

사용자: "졸려"
→ 많이 피곤하신가 봐요, 몸이 쉬라고 신호를 보내는 것 같아요.
"""


class ConversationV2:
    """시한부 환자 대화 엔진 - 템플릿 중심"""

    def __init__(self, user_id: str, profile: dict = None):
        self.user_id = user_id
        self.profile = profile or {}
        self.history: list[dict] = []
        self.stage = "S1" if not self._has_required_profile() else "S2"
        self.turn_count = 0

        self.empathy_df = pd.read_csv("./data/empathy_questions.csv")
        self.activities_df = pd.read_csv("./data/meaningful_activities.csv")

        self.asked_question_ids: set = set()
        self.prev_activity_names: set = set()

        self.session_start = datetime.now()
        self.last_visit = self._load_last_visit()
        self.first_visit = self.last_visit is None

        self.choice_asked = False
        self.waiting_for_choice = False

    def _has_required_profile(self) -> bool:
        """필수 프로필(A1, B1, A4) 채워졌는지 확인"""
        return all(k in self.profile for k in ["A1", "B1", "A4"])

    def get_profile_questions(self) -> list[dict]:
        """프로필 입력용 질문 목록 반환"""
        return [
            {"id": "A1", "text": "어떻게 불러드리면 편하실까요?", "type": "text"},
            {
                "id": "B1",
                "text": "요즘 마음 상태는 어떠신가요?",
                "type": "choice",
                "options": [
                    "불안하다",
                    "무기력하다",
                    "외롭다",
                    "혼란스럽다",
                    "슬프다",
                    "그래도 꽤 평온하다",
                    "말로 표현하기 어렵다",
                ],
            },
            {
                "id": "A4",
                "text": "평소 이동이나 움직임은 어느 정도 가능하신가요?",
                "type": "choice",
                "options": [
                    "걷기가 비교적 편하다",
                    "천천히라면 걷기는 가능하다",
                    "실내에서만 주로 움직인다",
                    "대부분 누워 지낸다",
                ],
            },
        ]

    def set_profile(self, answers: dict):
        """프로필 답변 저장 후 S2 진입 여부 결정"""
        self.profile.update(answers)
        if self._has_required_profile():
            self.stage = "S2"

    def _build_choice_sentence(self, last_user_message: str) -> str:
        """중간에 한 번 던지는 '대화 vs 활동' 선택 질문 문장 생성"""
        name = self.profile.get("A1", "")
        prefix = f"{name}님이" if name else "방금"
        return (
            f'{prefix} 말씀해 주신 "{last_user_message}"라는 말 속에 마음이 많이 담겨 있는 것 같아요. '
            f"지금처럼 계속 이야기를 조금 더 나눠볼까요, 아니면 지금 기분이 조금 나아질 만한 "
            f"작은 활동을 하나 추천해드릴까요?"
        )

    def _is_activity_request(self, text: str) -> bool:
        """사용자 발화가 직접적인 '활동/방법 추천' 요청인지 판단"""
        t = text.replace(" ", "")
        keywords = [
            "추천해줘",
            "추천해줄래",
            "뭘하면좋을까",
            "뭘하면좋아",
            "뭘하면좋지",
            "방법없을까",
            "방법추천",
            "어떻게하면좋아",
            "뭐하면좋아",
            "다른거추천",
            "다른거또추천",
        ]
        return any(k in t for k in keywords)

    def chat(self, user_message: str) -> dict:
        """사용자 메시지를 입력받아 챗봇 응답을 생성"""
        if self.stage != "S2":
            return {"response": f"현재 {self.stage} 단계입니다.", "stage": self.stage}

        if self.waiting_for_choice:
            self.history.append(
                {
                    "role": "user",
                    "content": user_message,
                    "timestamp": datetime.now().isoformat(),
                }
            )

            text = user_message.strip()
            activity_keywords = ["활동", "추천", "해볼게", "해볼까", "해줘", "2"]

            if any(k in text for k in activity_keywords):
                rec = self.recommend_activity()
                resp = rec["message"]
                self.waiting_for_choice = False

                self.history.append(
                    {
                        "role": "assistant",
                        "content": resp,
                        "timestamp": datetime.now().isoformat(),
                    }
                )

                return {
                    "response": resp,
                    "stage": "S2",
                    "mode": "activity",
                }

            resp = "그럼 계속해서 조금 더 이야기 나눠볼게요. 편하게 이어서 말씀해 주세요."
            self.waiting_for_choice = False

            self.history.append(
                {
                    "role": "assistant",
                    "content": resp,
                    "timestamp": datetime.now().isoformat(),
                }
            )

            return {
                "response": resp,
                "stage": "S2",
                "mode": "continue",
            }

        self.history.append(
            {
                "role": "user",
                "content": user_message,
                "timestamp": datetime.now().isoformat(),
            }
        )
        self.turn_count += 1

        if self._is_activity_request(user_message):
            rec = self.recommend_activity()
            resp = rec["message"]

            self.history.append(
                {
                    "role": "assistant",
                    "content": resp,
                    "timestamp": datetime.now().isoformat(),
                }
            )

            return {
                "response": resp,
                "stage": "S2",
                "mode": "activity_direct",
            }

        if (not self.choice_asked) and self.turn_count >= 3:
            self.choice_asked = True
            self.waiting_for_choice = True

            choice_sentence = self._build_choice_sentence(user_message)

            self.history.append(
                {
                    "role": "assistant",
                    "content": choice_sentence,
                    "timestamp": datetime.now().isoformat(),
                }
            )

            return {
                "response": choice_sentence,
                "stage": "S2",
                "mode": "choice",
            }

        should_ask = random.random() < 0.3
        question = self._get_question() if should_ask else None

        empathy = self._generate_simple_empathy(user_message)

        if question:
            ai_response = f"{empathy} {question}"
        else:
            followups = [
                "지금 하신 이야기에서 이어서 더 나누고 싶은 부분이 있으실까요?",
                "혹시 이 이야기와 관련해서 더 하고 싶은 말이 떠오르시나요?",
                "이 순간에 가장 먼저 떠오르는 생각이 있다면 어떤 걸까요?",
            ]
            ai_response = f"{empathy} {random.choice(followups)}"

        self.history.append(
            {
                "role": "assistant",
                "content": ai_response,
                "timestamp": datetime.now().isoformat(),
            }
        )

        return {
            "response": ai_response,
            "stage": "S2",
        }

    def _get_question(self) -> str | None:
        """empathy_questions.csv에서 stage에 맞는 질문 1개 선택"""
        if self.turn_count < 3:
            stage = "Stage1"
        elif self.turn_count < 6:
            stage = "Stage2"
        else:
            stage = "Stage3"

        available = self.empathy_df[
            (self.empathy_df["stage"] == stage)
            & (~self.empathy_df["question_id"].isin(self.asked_question_ids))
        ]

        if available.empty:
            return None

        selected = available.sample(n=1).iloc[0]
        self.asked_question_ids.add(selected["question_id"])
        return selected["question_text"]

    def _generate_simple_empathy(self, user_message: str) -> str:
        """사용자 발화를 기반으로 공감 1문장을 생성"""
        prompt = f"""사용자: "{user_message}"

위 말에 공감하는 한 문장을 만드세요.

규칙:
- 사용자가 말한 단어를 한 번 이상 포함
- "그렇군요", "좋으시겠네요" 같은 말 금지
- 1문장만
- 출력에는 따옴표(" "), 화살표(→), 예시 형식을 사용하지 마세요.
"""
        raw = generate_text(SIMPLE_PROMPT, prompt).strip()

        if "→" in raw:
            raw = raw.split("→")[-1].strip()

        for quote in ['"', "“", "”", "「", "」"]:
            if raw.startswith(quote):
                raw = raw[1:].lstrip()
            if raw.endswith(quote):
                raw = raw[:-1].rstrip()

        if len(raw) > 60:
            raw = raw[:60].rstrip() + "..."

        return raw

    def recommend_activity(self) -> dict:
        """프로필 기반으로 소규모 활동을 추천"""
        try:
            from recommend_ba import recommend_activities_from_user_profile
        except ImportError:
            return {
                "message": "지금은 활동 추천을 준비하지 못했어요. 그냥 편하게 쉬셔도 괜찮습니다.",
                "activities": [],
            }

        rec_df = recommend_activities_from_user_profile(
            self.profile,
            self.activities_df,
            conversation_stage="early",
        )

        if rec_df.empty:
            return {
                "message": "지금은 그냥 쉬시는 게 좋을 것 같아요.",
                "activities": [],
            }

        if "activity_kr" in rec_df.columns:
            filtered = rec_df[~rec_df["activity_kr"].isin(self.prev_activity_names)]
            use_df = filtered if not filtered.empty else rec_df
        else:
            use_df = rec_df

        activities = []
        for _, row in use_df.head(3).iterrows():
            name = row.get("activity_kr", "")
            category = row.get("category", "")
            activities.append(
                {
                    "name": name,
                    "category": category,
                }
            )
            if name:
                self.prev_activity_names.add(name)

        names = [a["name"] for a in activities if a["name"]]

        if names:
            message = (
                "이야기 나누다가 잠깐 숨 고르고 싶을 때는 이런 것들을 괜찮아 하셨던 분들도 계셨어요. "
                + ", ".join(names[:2])
            )
        else:
            message = "어떤 분들은 아주 사소한 것들을 하면서 잠깐 숨을 고르기도 하셨다고 해요."

        return {
            "message": message,
            "activities": activities,
        }

    def _load_last_visit(self) -> datetime | None:
        """마지막 방문 시간을 로드, 없으면 None 반환"""
        session_dir = Path("./sessions")
        session_dir.mkdir(exist_ok=True)
        user_file = session_dir / f"user_{self.user_id}_last.json"

        if user_file.exists():
            with open(user_file, "r") as f:
                data = json.load(f)
                return datetime.fromisoformat(data["last_visit"])
            
    

        return None


    def get_welcome_message(self) -> str:
        """사용자 마지막 방문 시점에 따른 환영 멘트 생성"""
        name = self.profile.get("A1", "")

        if self.first_visit:
            return f"{name}님, 처음 뵙네요." if name else "처음 뵙네요."

        if not self.last_visit:
            return f"{name}님, 반가워요." if name else "반가워요."

        days = (datetime.now() - self.last_visit).days

        if days == 0:
            return "다시 오셨네요."
        elif days == 1:
            return f"{name}님, 어제 이후로 어떠셨어요?" if name else "어제 이후로 어떠셨어요?"
        elif days < 7:
            return f"{name}님, {days}일 만이네요." if name else f"{days}일 만이네요."
        else:
            return f"{name}님, 오랜만이에요!" if name else "오랜만이에요!"

    def save_session(self):
        """현재 세션 대화 내용을 JSON 파일로 저장"""
        session_dir = Path("./sessions")
        session_dir.mkdir(exist_ok=True)

        session_id = self.session_start.strftime("%Y%m%d_%H%M%S")
        session_file = session_dir / f"user_{self.user_id}_session_{session_id}.json"

        session_data = {
            "user_id": self.user_id,
            "session_id": session_id,
            "profile": self.profile,
            "history": self.history,
            "timestamp": datetime.now().isoformat(),
        }

        with open(session_file, "w", encoding="utf-8") as f:
            json.dump(session_data, f, ensure_ascii=False, indent=2)

        last_file = session_dir / f"user_{self.user_id}_last.json"
        with open(last_file, "w") as f:
            json.dump({"last_visit": datetime.now().isoformat()}, f)
