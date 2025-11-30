import os
import json
import logging
import glob
from datetime import datetime
from typing import Dict, Any, List

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
            
        # 다이어리 저장 경로
        self.diary_path = os.path.join(storage_path, "diaries")
        if not os.path.exists(self.diary_path):
            os.makedirs(self.diary_path)

    def _get_file_path(self, user_id: str) -> str:
        return os.path.join(self.storage_path, f"{user_id}.json")

    def load_session(self, user_id: str) -> Dict[str, Any]:
        """세션 로드"""
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
        """세션 저장"""
        file_path = self._get_file_path(user_id)
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            logger.error(f"세션 저장 실패: {e}")

    def add_message(self, user_id: str, role: str, content: str):
        """대화 기록 추가"""
        session = self.load_session(user_id)
        message_entry = {
            "timestamp": datetime.now().isoformat(),
            "role": role,
            "content": content
        }
        session["conversation_history"].append(message_entry)
        self.save_session(user_id, session)

    def update_last_visit(self, user_id: str):
        """종료 시 방문 시간 업데이트"""
        session = self.load_session(user_id)
        session["last_visit"] = datetime.now().isoformat()
        self.save_session(user_id, session)

    def get_welcome_message(self, user_id: str) -> str:
        """환영 인사 생성"""
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
                return f"{title}, 다시 뵙게 되어 반갑습니다."
        except:
            return f"안녕하세요, {title}."

    def export_user_history(self, user_id: str) -> str:
        """오늘의 대화 기록 내보내기 (다이어리용)"""
        session = self.load_session(user_id)
        history = session.get("conversation_history", [])
        
        today = datetime.now().strftime("%Y-%m-%d")
        today_history = [
            msg for msg in history 
            if msg['timestamp'].startswith(today)
        ]
        
        lines = []
        for msg in today_history:
            role = "나" if msg['role'] == 'user' else "AI"
            time = msg['timestamp'][11:16] # HH:MM
            lines.append(f"[{time}] {role}: {msg['content']}")
            
        return "\n".join(lines) if lines else "오늘 나눈 대화가 없습니다."

    # --------------------------------------------------------------------------
    # [Feature] Diary Management Methods
    # --------------------------------------------------------------------------
    def _get_diary_path(self, user_id: str, date_str: str) -> str:
        # 파일명 예시: user123_2025-11-28.txt
        return os.path.join(self.diary_path, f"{user_id}_{date_str}.txt")

    def get_diary_entry(self, user_id: str, date_str: str) -> str:
        """해당 날짜의 다이어리 원본 텍스트 로드"""
        path = self._get_diary_path(user_id, date_str)
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                return f.read()
        return ""

    def save_diary_entry(self, user_id: str, date_str: str, content: str):
        """다이어리 저장 (덮어쓰기)"""
        path = self._get_diary_path(user_id, date_str)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)

    def delete_diary_entry(self, user_id: str, date_str: str) -> bool:
        """
        [NEW] 다이어리 삭제
        성공 시 True, 파일이 없어 실패 시 False 반환
        """
        path = self._get_diary_path(user_id, date_str)
        if os.path.exists(path):
            try:
                os.remove(path)
                logger.info(f"다이어리 삭제 완료: {path}")
                return True
            except Exception as e:
                logger.error(f"다이어리 삭제 중 오류: {e}")
                return False
        else:
            logger.warning(f"삭제할 다이어리가 없음: {path}")
            return False

    def get_all_diaries_metadata(self, user_id: str) -> List[Dict[str, str]]:
        """캘린더 UI용 메타데이터 추출"""
        diary_files = glob.glob(os.path.join(self.diary_path, f"{user_id}_*.txt"))
        metadata_list = []

        for file_path in diary_files:
            try:
                filename = os.path.basename(file_path)
                date_part = filename.replace(f"{user_id}_", "").replace(".txt", "")
                
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    lines = content.split('\n')
                    
                    first_line = lines[0] if lines else ""
                    emoji = "📝"
                    tags = ""
                    
                    if "]" in first_line:
                        parts = first_line.split("]", 1)
                        meta_part = parts[1].strip()
                        tokens = meta_part.split()
                        if tokens:
                            emoji = tokens[0]
                            tags = " ".join([t for t in tokens if t.startswith("#")])
                    
                    metadata_list.append({
                        "date": date_part,
                        "emoji": emoji,
                        "tags": tags,
                        "preview": content[:50] + "..."
                    })
            except Exception as e:
                logger.error(f"다이어리 메타데이터 파싱 실패 ({file_path}): {e}")
                continue
        
        metadata_list.sort(key=lambda x: x["date"])
        return metadata_list