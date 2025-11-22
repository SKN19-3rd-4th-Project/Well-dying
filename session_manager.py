
import os
import json
import glob
from datetime import datetime
from typing import Optional
import logging

logging.basicConfig(level=logging.INFO)

class SessionManager:
    """
    사용자별 세션을 관리하는 클래스
    - 세션 저장/로드
    - 사용자별 세션 이력 조회
    - 마지막 세션 자동 로드
    """
    
    def __init__(self, sessions_dir: str = "./sessions"):
        self.sessions_dir = sessions_dir
        os.makedirs(sessions_dir, exist_ok=True)
    
    def save_session(self, engine_state: dict, user_id: str = None) -> str:
        """
        세션을 파일로 저장
        user_id가 없으면 session_id만 사용
        """
        session_id = engine_state.get("session_id", datetime.now().strftime("%Y%m%d_%H%M%S"))
        
        if user_id:
            filename = f"user_{user_id}_session_{session_id}.json"
        else:
            filename = f"session_{session_id}.json"
        
        filepath = os.path.join(self.sessions_dir, filename)
        
        # 사용자 정보 추가
        engine_state["user_id"] = user_id
        
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(engine_state, f, ensure_ascii=False, indent=2)
        
        logging.info(f"💾 세션 저장: {filepath}")
        return filepath
    
    def load_session(self, filepath: str) -> Optional[dict]:
        """
        세션 파일 로드
        """
        if not os.path.exists(filepath):
            logging.error(f"세션 파일을 찾을 수 없습니다: {filepath}")
            return None
        
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                state = json.load(f)
            
            logging.info(f"📂 세션 로드: {filepath}")
            return state
        except json.JSONDecodeError as e:
            logging.error(f"세션 파일 파싱 오류: {e}")
            return None
    
    def get_user_sessions(self, user_id: str) -> list[dict]:
        """
        특정 사용자의 모든 세션 조회 (최신순)
        """
        pattern = os.path.join(self.sessions_dir, f"user_{user_id}_session_*.json")
        files = glob.glob(pattern)
        
        sessions = []
        for filepath in files:
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    state = json.load(f)
                    sessions.append({
                        "filepath": filepath,
                        "session_id": state.get("session_id"),
                        "timestamp": state.get("timestamp"),
                        "state": state.get("state"),
                    })
            except Exception as e:
                logging.warning(f"세션 파일 읽기 실패: {filepath}, {e}")
        
        # 최신순 정렬
        sessions.sort(key=lambda x: x["timestamp"], reverse=True)
        
        return sessions
    
    def get_last_session(self, user_id: str) -> Optional[dict]:
        """
        사용자의 마지막 세션 로드
        """
        sessions = self.get_user_sessions(user_id)
        
        if not sessions:
            logging.info(f"사용자 {user_id}의 세션이 없습니다.")
            return None
        
        last_session_file = sessions[0]["filepath"]
        return self.load_session(last_session_file)
    
    def count_user_sessions(self, user_id: str) -> int:
        """
        사용자의 총 세션 수 반환
        """
        return len(self.get_user_sessions(user_id))
    
    def delete_session(self, filepath: str) -> bool:
        """
        세션 파일 삭제
        """
        try:
            os.remove(filepath)
            logging.info(f"🗑️ 세션 삭제: {filepath}")
            return True
        except Exception as e:
            logging.error(f"세션 삭제 실패: {e}")
            return False
    
    def export_user_history(self, user_id: str, output_file: str = None):
        """
        사용자의 전체 대화 이력을 하나의 파일로 내보내기
        """
        sessions = self.get_user_sessions(user_id)
        
        if not sessions:
            logging.warning(f"사용자 {user_id}의 세션이 없습니다.")
            return None
        
        # 모든 세션의 대화 내역 결합
        all_history = []
        
        for session_info in sessions:
            state = self.load_session(session_info["filepath"])
            if state:
                all_history.append({
                    "session_id": state.get("session_id"),
                    "timestamp": state.get("timestamp"),
                    "dialog_history": state.get("dialog_history", []),
                })
        
        # 파일로 저장
        if output_file is None:
            output_file = os.path.join(self.sessions_dir, f"user_{user_id}_history.json")
        
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(all_history, f, ensure_ascii=False, indent=2)
        
        logging.info(f"📜 사용자 이력 내보내기: {output_file}")
        return output_file


# =====================================================
# 사용 예시
# =====================================================

if __name__ == "__main__":
    manager = SessionManager()
    
    # 예시: 사용자 "alice"의 세션 조회
    user_id = "alice"
    
    print(f"\n{'='*50}")
    print(f"사용자 {user_id}의 세션 조회")
    print(f"{'='*50}")
    
    sessions = manager.get_user_sessions(user_id)
    print(f"총 {len(sessions)}개 세션")
    
    for i, s in enumerate(sessions, 1):
        print(f"{i}. {s['timestamp']} - {s['state']}")
    
    # 마지막 세션 로드
    if sessions:
        print(f"\n마지막 세션 로드 중...")
        last = manager.get_last_session(user_id)
        if last:
            print(f"✅ 세션 ID: {last['session_id']}")
            print(f"   상태: {last['state']}")
            print(f"   대화 기록 수: {len(last.get('dialog_history', []))}")