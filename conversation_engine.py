import json
import random
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional

import pandas as pd

from llm_client import generate_text
from recommend_ba import recommend_activities_from_user_profile


# ============================================================
#   CONFIG 
# ============================================================

DIALOG_POLICY = {
    "offer_choice_min_turn": 3,
    "offer_choice_max_turn": 6,

    "question_prob": {
        "early": 0.9,
        "middle": 0.6,
        "late": 0.3
    }
}

STOP_WORDS = ["그만", "끝", "나가기", "종료", "exit", "quit"]

HARSH_WORDS = ["죽고", "너무 힘들", "버거워", "감당이 안 돼", "절망"]

ACTIVITY_REQUEST_KEYWORDS = [
    "활동 추천", "활동 하나 추천",
    "할 만한 활동", "할만한 활동",
    "뭐 하면 좋을까", "뭐 하면 좋을지",
    "뭘 하면 좋을까", "뭘 하면 좋을지",
    "할 만한 게 있을까", "할 만한 거 있을까", "할만한 거 있을까",
    "뭐 할지 모르겠어",
]


# ============================================================
#   SYSTEM PROMPTS (너가 쓰던 원본 그대로)
# ============================================================

MAIN_SYSTEM_PROMPT = """
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
"""


# ============================================================
#   MAIN ENGINE
# ============================================================

class ConversationEngine:
    """시한부/노년층 대상 공감 대화 + 활동 추천 엔진"""

    def __init__(self, user_id: str, profile: Optional[Dict] = None):
        self.user_id = user_id
        self.profile: Dict = profile or {}
        self.history: List[Dict] = []

        self.stage = "S1" if not self._has_required_profile() else "S2"
        self.turn_count = 0

        try:
            self.empathy_df = pd.read_csv("./data/empathy_questions.csv")
        except Exception as e:
            print("[경고] empathy_questions.csv 로드 실패:", e)
            self.empathy_df = pd.DataFrame()

        try:
            self.activities_df = pd.read_csv("./data/meaningful_activities.csv")
        except Exception as e:
            print("[경고] meaningful_activities.csv 로드 실패:", e)
            self.activities_df = pd.DataFrame()

        self.asked_question_ids = set()
        self.offered_activity_choice = False
        self.offered_activities: List[str] = []

        self.session_start = datetime.now()
        self.last_visit = self._load_last_visit()

    # ===================== 프로필 =====================

    def _has_required_profile(self) -> bool:
        return all(k in self.profile for k in ["A1", "B1", "A4"])

    # ===================== 환영 멘트 =====================

    def get_welcome_message(self) -> str:
        name = self.profile.get("A1", "")
        title = f"{name}님" if name else "회원님"

        if self.last_visit.year < 2024:
            return f"안녕하세요, {title}. 오늘은 조금 어떠셨어요?"

        days = (datetime.now() - self.last_visit).days
        if days == 0:
            return "다시 오셨군요. 천천히 이야기 나눠봐요."
        if days == 1:
            return f"{title}, 밤사이 편안하셨나요?"
        return f"{title}, 다시 뵙게 되어 반갑습니다."

    # ===================== 메인 대화 =====================

    def chat(self, user_message: str) -> Dict:
        text = (user_message or "").strip()

        if not text:
            return {"response": "천천히 말씀하셔도 괜찮아요. 저는 여기에서 기다리고 있겠습니다.", "stage": self.stage}

        if self._is_stop_signal(text):
            resp = "네, 오늘은 여기까지만 할까요. 함께해 주셔서 고맙습니다."
            self._append_history("user", text)
            self._append_history("assistant", resp)
            return {"response": resp, "stage": "END", "end": True}

        if self.stage != "S2":
            return {"response": "먼저 프로필 몇 가지만 정리한 뒤에, 천천히 이야기를 이어가면 좋을 것 같아요.", "stage": "S1"}

        self.turn_count += 1
        self._append_history("user", text)

        # 활동 직접 요청
        if self._is_activity_request(text):
            resp = self._build_activity_reply(text)
            self._append_history("assistant", resp)
            return {"response": resp, "stage": "S2", "mode": "activity_direct"}

        # 활동/대화 선택지 제안
        if self._should_offer_activity_choice(text):
            resp = self._build_activity_choice_reply(text)
            self.offered_activity_choice = True
            self._append_history("assistant", resp)
            return {"response": resp, "stage": "S2", "mode": "offer_choice"}

        # 기본 공감
        guide_q = self._pick_empathy_question()
        resp = self._build_main_reply(text, guide_q)
        self._append_history("assistant", resp)
        return {"response": resp, "stage": "S2", "mode": "dialogue"}

    # ===================== 감지 로직 =====================

    def _is_stop_signal(self, text: str) -> bool:
        return text.strip() in STOP_WORDS

    def _is_activity_request(self, text: str) -> bool:
        text = text.strip()
        return any(k in text for k in ACTIVITY_REQUEST_KEYWORDS)

    def _should_offer_activity_choice(self, text: str) -> bool:
        if self.turn_count < DIALOG_POLICY["offer_choice_min_turn"]:
            return False

        if self.offered_activity_choice:
            return False

        if any(h in text for h in HARSH_WORDS):
            return False

        return (
            DIALOG_POLICY["offer_choice_min_turn"]
            <= self.turn_count
            <= DIALOG_POLICY["offer_choice_max_turn"]
        )

    # ===================== CSV 질문 선택 =====================

    def _pick_empathy_question(self) -> Optional[str]:
        if self.empathy_df.empty:
            return None

        if self.turn_count <= 3:
            prob = DIALOG_POLICY["question_prob"]["early"]
        elif self.turn_count <= 7:
            prob = DIALOG_POLICY["question_prob"]["middle"]
        else:
            prob = DIALOG_POLICY["question_prob"]["late"]

        if random.random() > prob:
            return None

        if self.turn_count <= 2:
            stage = "Stage1"
        elif self.turn_count <= 5:
            stage = "Stage2"
        else:
            stage = "Stage3"

        cand = self.empathy_df[
            (self.empathy_df["stage"] == stage)
            & (~self.empathy_df["question_id"].isin(self.asked_question_ids))
        ]

        if cand.empty:
            return None

        row = cand.sample(1).iloc[0]
        self.asked_question_ids.add(row["question_id"])
        return str(row["question_text"])

    # ===================== 메인 응답 =====================

    def _build_main_reply(self, user_message: str, guide_q: Optional[str]) -> str:
        recent = self._format_recent_history(max_turns=3)
        name = self.profile.get("A1", "회원님")
        emotion = self.profile.get("B1", "")

        if guide_q:
            q_block = f"""
[참고 질문 후보]
- "{guide_q}"

[질문 사용 규칙]
- 자연스럽다면 마지막 문장을 이 질문으로 바꿔 사용.
- 어울리지 않으면 질문 없이 공감만."""
        else:
            q_block = """
[참고 질문 후보 없음]
- 이번에는 질문 없이 공감만으로 충분합니다.
"""

        prompt = f"""
[내담자 정보]
- 이름: {name}
- 현재 마음 상태(B1): {emotion}

[최근 대화]
{recent}

[내담자의 현재 말]
"{user_message}"

{q_block}

[작성 지침]
- 감정을 반복하거나 분석하지 말 것.
- 반말 금지.
- 숙제/권유 금지.
- 2~3문장, 따뜻한 톤.
"""

        return generate_text(MAIN_SYSTEM_PROMPT, prompt).strip()

    # ===================== 선택지 제안 =====================

    def _build_activity_choice_reply(self, user_message: str) -> str:
        name = self.profile.get("A1", "회원님")

        prompt = f"""
[내담자 이름] {name}
[내담자의 마지막 말] "{user_message}"

1문장: 지금 마음에 조용히 공감하기.
2문장: 아래 스타일처럼 선택지를 제안하기.
 - "혹시 괜찮으시다면, 중간에 작은 활동을 하나 골라볼까요?"
 - "물론 지금처럼 이야기를 이어가셔도 괜찮아요."

총 2~3문장.
"""

        return generate_text(CHOICE_SYSTEM_PROMPT, prompt).strip()

    # ===================== 활동 추천 =====================

    def _build_activity_reply(self, user_message: str) -> str:
        rec_df = recommend_activities_from_user_profile(
            self.profile, self.activities_df, conversation_stage="middle"
        )

        if rec_df.empty:
            return "지금은 잠시 기대어 쉬어가는 시간이 더 필요하실 수도 있겠다는 생각이 들어요."

        rec_df = rec_df[~rec_df["activity_kr"].isin(self.offered_activities)]

        if rec_df.empty:
            return "이전에 드렸던 활동들이 마음에 들지 않으셨을 수도 있을 것 같아요. 지금은 그냥 잠시 쉬어가도 괜찮을까요?"

        sample = rec_df.head(2)
        for _, row in sample.iterrows():
            self.offered_activities.append(row["activity_kr"])
        self.offered_activities = self.offered_activities[-5:]

        items = [f"- {row['activity_kr']}" for _, row in sample.iterrows()]
        candidates = "\n".join(items)

        prompt = f"""
[내담자 요청]
"{user_message}"

[활동 예시]
{candidates}

지침:
- 1~2개만 언급
- '혹시 괜찮으시다면' 사용
- 부드럽고 선택 기반
- 3~4문장
"""

        return generate_text(ACTIVITY_SYSTEM_PROMPT, prompt).strip()

    # ===================== HISTORY 관리 =====================

    def _format_recent_history(self, max_turns: int = 3) -> str:
        recent = self.history[-max_turns*2:]
        lines = []
        for h in recent:
            role = "사용자" if h["role"] == "user" else "AI"
            lines.append(f"{role}: {h['content']}")
        return "\n".join(lines) if lines else "(대화 시작)"

    def _append_history(self, role: str, content: str) -> None:
        self.history.append({
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat()
        })

    def _load_last_visit(self) -> datetime:
        path = Path(f"./sessions/user_{self.user_id}_last.json")
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return datetime.fromisoformat(data["last_visit"])
            except:
                pass
        return datetime(2000, 1, 1)

    def save_session(self) -> None:
        session_dir = Path("./sessions")
        session_dir.mkdir(exist_ok=True)

        session_id = self.session_start.strftime("%Y%m%d_%H%M%S")
        path = session_dir / f"user_{self.user_id}_session_{session_id}.json"

        data = {
            "user_id": self.user_id,
            "session_id": session_id,
            "profile": self.profile,
            "history": self.history,
            "timestamp": datetime.now().isoformat(),
        }

        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        last_file = session_dir / f"user_{self.user_id}_last.json"
        with open(last_file, "w", encoding="utf-8") as f:
            json.dump({"last_visit": datetime.now().isoformat()}, f, ensure_ascii=False)
