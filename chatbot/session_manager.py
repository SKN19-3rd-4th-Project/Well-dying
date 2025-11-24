import os
import json
import logging
from datetime import datetime
from typing import Dict, Any, Optional

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SessionManager:
    """
    사용자 데이터 및 세션 관리 클래스
    - 파일 시스템 기반 저장소
    - 대화 이력 및 방문 시간 관리
    """
    def __init__(self, storage_path: str = "sessions"):
        self.storage_path = storage_path
        if not os.path.exists(storage_path):
            os.makedirs(storage_path)

    def _get_file_path(self, user_id: str) -> str:
        return os.path.join(self.storage_path, f"{user_id}.json")

    def load_session(self, user_id: str) -> Dict[str, Any]:
        """사용자 세션 로드 (없으면 기본 구조 생성)"""
        file_path = self._get_file_path(user_id)
        if os.path.exists(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    session = json.load(f)
                    # 호환성: last_visit 필드가 없으면 None으로 초기화
                    if "last_visit" not in session:
                        session["last_visit"] = None
                    return session
            except Exception as e:
                logger.error(f"세션 로드 실패: {e}")
        
        # 신규 사용자 기본 구조
        return {
            "user_id": user_id,
            "last_visit": None,  # 마지막 방문 시간 (ISO format string)
            "user_profile": {
                "name": "사용자", # A1에 해당
                "age": "미상",
                "mobility": "거동 가능",
                "family": "정보 없음"
            },
            "conversation_history": []
        }

    def save_session(self, user_id: str, data: Dict[str, Any]):
        """세션 데이터 저장"""
        file_path = self._get_file_path(user_id)
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            logger.error(f"세션 저장 실패: {e}")

    def add_message(self, user_id: str, role: str, content: str):
        """대화 내용 영구 저장"""
        session = self.load_session(user_id)
        message_entry = {
            "timestamp": datetime.now().isoformat(),
            "role": role,
            "content": content
        }
        session["conversation_history"].append(message_entry)
        self.save_session(user_id, session)

    def update_last_visit(self, user_id: str):
        """
        [New] 챗봇 종료 시 호출: 현재 시간을 마지막 방문 시간으로 저장
        """
        session = self.load_session(user_id)
        session["last_visit"] = datetime.now().isoformat()
        self.save_session(user_id, session)
        logger.info(f"[{user_id}] 마지막 방문 시간 업데이트 완료")

    def get_welcome_message(self, user_id: str) -> str:
        """
        [New] 챗봇 시작 시 호출: 마지막 방문 시간에 따른 환영 인사 반환
        """
        session = self.load_session(user_id)
        profile = session.get("user_profile", {})
        last_visit_str = session.get("last_visit")
        
        name = profile.get("name", "")
        # 이름이 '사용자'거나 없으면 '회원님'으로 호칭
        title = f"{name}님" if name and name != "사용자" else "회원님"

        # 1. 첫 방문이거나 기록이 없는 경우
        if not last_visit_str:
            return f"안녕하세요, {title}. 오늘은 어떠셨어요?"

        # 2. 날짜 차이 계산
        try:
            last_visit = datetime.fromisoformat(last_visit_str)
            days_diff = (datetime.now() - last_visit).days
            
            if days_diff == 0:
                return "다시 오셨군요. 천천히 이야기 나눠봐요."
            elif days_diff == 1:
                return f"{title}, 밤 사이 편안하셨나요?"
            else:
                return f"{title}, 다시 뵙게 되어 반갑습니다."
                
        except ValueError:
            # 날짜 파싱 에러 시 기본 메시지
            return f"안녕하세요, {title}. 오늘도 찾아와주셔서 감사합니다."

    def export_user_history(self, user_id: str) -> str:
        """다이어리 생성을 위한 대화 기록 내보내기"""
        session = self.load_session(user_id)
        history = session.get("conversation_history", [])
        
        lines = []
        for msg in history:
            role_name = "나" if msg['role'] == 'user' else "AI"
            time_str = msg['timestamp'][:16].replace("T", " ")
            lines.append(f"[{time_str}] {role_name}: {msg['content']}")
            
        return "\n".join(lines) if lines else "대화 기록이 없습니다."