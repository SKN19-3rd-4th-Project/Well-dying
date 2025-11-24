import os
import json
import logging
from datetime import datetime
from typing import Dict, Any

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SessionManager:
    """
    사용자 세션 및 기록 관리
    """
    def __init__(self, storage_path: str = "sessions"):
        self.storage_path = storage_path
        if not os.path.exists(storage_path):
            os.makedirs(storage_path)

    def _get_file_path(self, user_id: str) -> str:
        return os.path.join(self.storage_path, f"{user_id}.json")

    def load_session(self, user_id: str) -> Dict[str, Any]:
        """세션 로드 (호환성 보장)"""
        file_path = self._get_file_path(user_id)
        if os.path.exists(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    session = json.load(f)
                    if "last_visit" not in session:
                        session["last_visit"] = None
                    return session
            except Exception as e:
                logger.error(f"세션 로드 실패: {e}")
        
        # 기본 세션 구조
        return {
            "user_id": user_id,
            "last_visit": None,
            "user_profile": {
                "name": "사용자",
                "age": "미상",
                "mobility": "거동 가능",
                "family": "정보 없음"
            },
            "conversation_history": []
        }

    def save_session(self, user_id: str, data: Dict[str, Any]):
        file_path = self._get_file_path(user_id)
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            logger.error(f"세션 저장 실패: {e}")

    def add_message(self, user_id: str, role: str, content: str):
        """
        대화 기록 추가
        시간순으로 대화 내역을 보존
        """
        session = self.load_session(user_id)
        message_entry = {
            "timestamp": datetime.now().isoformat(),
            "role": role,
            "content": content
        }
        session["conversation_history"].append(message_entry)
        self.save_session(user_id, session)

    def update_last_visit(self, user_id: str):
        """종료 시 마지막 방문 시간 업데이트"""
        session = self.load_session(user_id)
        session["last_visit"] = datetime.now().isoformat()
        self.save_session(user_id, session)

    def get_welcome_message(self, user_id: str) -> str:
        """
        환영 인사
        재접속 간격에 따른 반응 생성
        0: 24시간 이내 / 1: 하루 / 2~: 장시간 / 기타: 첫만남
        """
        session = self.load_session(user_id)
        name = session.get("user_profile", {}).get("name", "")
        last_visit_str = session.get("last_visit")
        
        title = f"{name}님" if name and name != "사용자" else "회원님"

        if not last_visit_str:
            return f"안녕하세요, {title}. 오늘은 좀 어떠신가요?"

        try:
            days_diff = (datetime.now() - datetime.fromisoformat(last_visit_str)).days
            if days_diff == 0:
                return "다시 오셨군요. 이야기를 계속 나눠볼까요?"
            elif days_diff == 1:
                return f"{title}, 밤사이 편안하셨나요?"
            else:
                return f"{title}, 오랜만에 오셨네요!"
        except:
            return f"안녕하세요, {title}."

    def export_user_history(self, user_id: str) -> str:
        """다이어리 생성을 위한 기록 추출"""
        session = self.load_session(user_id)
        history = session.get("conversation_history", [])
        
        lines = []
        for msg in history:
            role = "나" if msg['role'] == 'user' else "AI"
            time = msg['timestamp'][:16].replace("T", " ")
            lines.append(f"[{time}] {role}: {msg['content']}")
            
        return "\n".join(lines) if lines else "대화 기록 없음"