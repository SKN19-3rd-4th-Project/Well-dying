# main.py - FastAPI 서버 (LangGraph 기반 백엔드)

import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import csv

import jwt
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# Allow running from repo root or ./chatbot directory
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.conversation_engine import ConversationEngine
from scripts.session_manager import SessionManager

# Paths for serving frontend
FRONTEND_DIR = Path(__file__).resolve().parent
ASSETS_DIR = FRONTEND_DIR / "assets"

app = FastAPI(title="Lifeclover API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static frontend so one server is enough
if ASSETS_DIR.exists():
    app.mount("/assets", StaticFiles(directory=ASSETS_DIR), name="assets")

# Load environment variables from .env if present
load_dotenv()

SECRET_KEY = os.getenv("JWT_SECRET_KEY", "your-secret-key-change-this")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24

security = HTTPBearer()

session_manager = SessionManager()
engine = ConversationEngine()

USERS_FILE = Path("./data/users.json")
if not USERS_FILE.exists():
    USERS_FILE.parent.mkdir(exist_ok=True)
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump({}, f)


class RegisterRequest(BaseModel):
    user_id: str
    password: str
    name: Optional[str] = None


class LoginRequest(BaseModel):
    user_id: str
    password: str


class ChatRequest(BaseModel):
    message: str
    mode: Optional[str] = "chat"


class ProfileRequest(BaseModel):
    profile: Dict[str, Any]


class ChatResponse(BaseModel):
    response: str
    stage: str = "S2"
    mode: Optional[str] = None
    timestamp: str


class ChecklistItem(BaseModel):
    question_id: str
    section: str
    category: str
    question_kr: str
    input_type: str
    options_kr: Optional[str] = None


def load_users() -> Dict:
    try:
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_users(users: Dict):
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, ensure_ascii=False, indent=2)


def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> str:
    try:
        token = credentials.credentials
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        return user_id
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")


def sync_session_profile(user_id: str) -> Optional[Dict[str, Any]]:
    """사용자 프로필을 세션 스토리지와 동기화."""
    users = load_users()
    profile = users.get(user_id, {}).get("profile")
    if profile:
        session_manager.update_user_profile(user_id, profile)
    return profile


@app.get("/")
async def serve_index():
    index_path = FRONTEND_DIR / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    return {"service": "Lifeclover API", "status": "running", "version": "2.0.0"}


@app.get("/api/health")
async def health():
    return {"service": "Lifeclover API", "status": "running", "version": "2.0.0"}


@app.post("/api/auth/register")
async def register(req: RegisterRequest):
    users = load_users()

    if req.user_id in users:
        raise HTTPException(status_code=400, detail="User already exists")

    users[req.user_id] = {
        "password": req.password,
        "name": req.name or req.user_id,
        "profile": {},
        "created_at": datetime.now().isoformat(),
    }

    save_users(users)

    token = create_access_token({"sub": req.user_id})

    return {
        "message": "User registered successfully",
        "user_id": req.user_id,
        "token": token,
    }


@app.post("/api/auth/login")
async def login(req: LoginRequest):
    users = load_users()

    if req.user_id not in users:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    user = users[req.user_id]

    if user["password"] != req.password:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    sync_session_profile(req.user_id)

    token = create_access_token({"sub": req.user_id})

    return {
        "message": "Login successful",
        "user_id": req.user_id,
        "name": user.get("name"),
        "token": token,
        "has_profile": bool(user.get("profile")),
    }


@app.get("/api/checklist")
async def get_checklist(user_id: str = Depends(verify_token)):
    try:
        checklist: List[Dict[str, Any]] = []
        with open("./data/user_profile_checklist.csv", "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Ensure missing fields become empty strings
                row = {k: (v if v is not None else "") for k, v in row.items()}
                item = ChecklistItem(
                    question_id=row.get("question_id", ""),
                    section=row.get("section", ""),
                    category=row.get("category", ""),
                    question_kr=row.get("question_kr", ""),
                    input_type=row.get("input_type", ""),
                    options_kr=row.get("options_kr", "") or "",
                )
                checklist.append(item.model_dump())

        return {"checklist": checklist}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load checklist: {str(e)}")


@app.post("/api/profile")
async def save_profile(req: ProfileRequest, user_id: str = Depends(verify_token)):
    users = load_users()

    if user_id not in users:
        raise HTTPException(status_code=404, detail="User not found")

    users[user_id]["profile"] = req.profile
    save_users(users)
    session_manager.update_user_profile(user_id, req.profile)

    return {"message": "Profile saved successfully", "profile": req.profile}


@app.get("/api/profile")
async def get_profile(user_id: str = Depends(verify_token)):
    users = load_users()

    if user_id not in users:
        raise HTTPException(status_code=404, detail="User not found")

    return {"profile": users[user_id].get("profile", {})}


@app.get("/api/welcome")
async def get_welcome_message(user_id: str = Depends(verify_token)):
    sync_session_profile(user_id)
    welcome_msg = session_manager.get_welcome_message(user_id)
    return {"message": welcome_msg, "stage": "S2"}


@app.post("/api/chat")
async def chat(req: ChatRequest, user_id: str = Depends(verify_token)):
    try:
        sync_session_profile(user_id)
        mode = req.mode or "chat"
        response_text = engine.process_user_message(user_id, req.message, mode=mode)

        return ChatResponse(
            response=response_text,
            stage="S2",
            mode=mode,
            timestamp=datetime.now().isoformat(),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Chat failed: {str(e)}")


@app.get("/api/history")
async def get_history(user_id: str = Depends(verify_token)):
    try:
        session = session_manager.load_session(user_id)
        return {
            "history": session.get("conversation_history", []),
            "last_visit": session.get("last_visit"),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load history: {str(e)}")


@app.get("/api/sessions")
async def get_sessions(user_id: str = Depends(verify_token)):
    sessions = session_manager.get_user_sessions(user_id)
    return {"sessions": sessions}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
