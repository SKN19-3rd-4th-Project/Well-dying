import os
import json
import logging
from datetime import datetime
from typing import Dict, Any, List

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SessionManager:
    """간단한 파일 기반 세션/프로필 관리기."""

    def __init__(self, storage_path: str = "sessions"):
        self.storage_path = storage_path
        if not os.path.exists(storage_path):
            os.makedirs(storage_path)

    def _get_file_path(self, user_id: str) -> str:
        return os.path.join(self.storage_path, f"{user_id}.json")

    def load_session(self, user_id: str) -> Dict[str, Any]:
        """세션 로드 (필요 필드가 없으면 기본값 채움)."""
        file_path = self._get_file_path(user_id)
        if os.path.exists(file_path):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    session = json.load(f)
                    session.setdefault("last_visit", None)
                    session.setdefault("conversation_history", [])
                    session.setdefault(
                        "user_profile",
                        {
                            "name": "",
                            "age": "",
                            "mobility": "",
                            "activity_range": "",
                        },
                    )
                    return session
            except Exception as e:
                logger.error(f"세션 로드 실패: {e}")

        return {
            "user_id": user_id,
            "last_visit": None,
            "user_profile": {
                "name": "",
                "mobility": "",
                "emotion": "",
            },
            "conversation_history": [],
        }

    def save_session(self, user_id: str, data: Dict[str, Any]):
        file_path = self._get_file_path(user_id)
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            logger.error(f"세션 저장 실패: {e}")

    def _normalize_profile(self, profile: Dict[str, Any], current: Dict[str, Any]) -> Dict[str, Any]:
        """
        Map checklist answers into explicit profile fields.
        """
        normalized = {**current, **(profile or {})}
        name = profile.get("name") or profile.get("A1")
        if name:
            normalized["name"] = name
        mobility = profile.get("mobility") or profile.get("A2") or profile.get("A4")
        activity_range = profile.get("activity_range") or profile.get("A2") or profile.get("A4")
        emotion = profile.get("emotion") or profile.get("B1")
        if mobility:
            normalized["mobility"] = mobility
        if activity_range:
            normalized["activity_range"] = activity_range
        if emotion:
            normalized["emotion"] = emotion
        return normalized

    def add_message(self, user_id: str, role: str, content: str):
        """대화 기록 추가."""
        session = self.load_session(user_id)
        message_entry = {
            "timestamp": datetime.now().isoformat(),
            "role": role,
            "content": content,
        }
        session["conversation_history"].append(message_entry)
        self.save_session(user_id, session)

    def update_last_visit(self, user_id: str):
        """마지막 방문 시간 업데이트."""
        session = self.load_session(user_id)
        session["last_visit"] = datetime.now().isoformat()
        self.save_session(user_id, session)

    def update_user_profile(self, user_id: str, profile: Dict[str, Any]):
        """외부에서 프로필을 변경할 때 사용."""
        session = self.load_session(user_id)
        session["user_profile"] = self._normalize_profile(profile, session.get("user_profile", {}))
        self.save_session(user_id, session)

    def get_welcome_message(self, user_id: str) -> str:
        """재접속 간격에 따른 환영 인사 생성."""
        session = self.load_session(user_id)
        name = session.get("user_profile", {}).get("name", "") or session.get("user_profile", {}).get("A1", "")
        last_visit_str = session.get("last_visit")

        title = f"{name}님" if name else "님"

        if not last_visit_str:
            return f"안녕하세요, {title} 오늘은 좀 어떠신가요?"

        try:
            days_diff = (datetime.now() - datetime.fromisoformat(last_visit_str)).days
            if days_diff == 0:
                return f"{title} 다시 오셨군요. 이야기를 계속 나눠볼까요?"
            if days_diff == 1:
                return f"{title} 밤사이 편안하셨나요?"
            return f"{title} 오랜만에 오셨네요!"
        except Exception:
            return f"안녕하세요, {title}"

    def get_user_sessions(self, user_id: str) -> List[Dict[str, Any]]:
        """
        호환용: 단일 세션 파일 기반이므로 하나의 요약을 리스트로 반환.
        """
        session = self.load_session(user_id)
        return [
            {
                "user_id": user_id,
                "last_visit": session.get("last_visit"),
                "messages": session.get("conversation_history", []),
            }
        ]
