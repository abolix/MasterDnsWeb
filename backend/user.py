from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel
from datetime import datetime, timedelta, timezone
from pathlib import Path
from jose import JWTError, jwt
import os
import sys

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:
    def load_dotenv(*args, **kwargs):
        return False


user_router = APIRouter(tags=["user"])

def _app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent

load_dotenv(dotenv_path=_app_dir() / ".env", override=False)
ALGORITHM = "HS256"
SECRET_KEY = os.getenv("SECRET_KEY", "default-change-this-in-production")
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "password")
TOKEN_EXPIRATION_DAYS = 365  # One year
SESSION_COOKIE_NAME = os.getenv("SESSION_COOKIE_NAME", "masterdnsweb_session")
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"
COOKIE_SAMESITE = os.getenv("COOKIE_SAMESITE", "lax")

class LoginRequest(BaseModel):
    username: str
    password: str

class LoginResponse(BaseModel):
    access_token: str

class UserInfoResponse(BaseModel):
    username: str

def verify_token(token: str) -> str:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("username")
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session"
        ) from exc

    if not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid session payload"
        )
    return username

def get_token_from_request(request: Request) -> str:
    cookie_token = request.cookies.get(SESSION_COOKIE_NAME)
    if cookie_token:
        return cookie_token

    authorization = request.headers.get("Authorization", "")
    if authorization.startswith("Bearer "):
        return authorization.removeprefix("Bearer ").strip()

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated"
    )

def get_current_username(request: Request) -> str:
    token = get_token_from_request(request)
    return verify_token(token)

def set_session_cookie(response: Response, token: str) -> None:
    max_age = TOKEN_EXPIRATION_DAYS * 24 * 60 * 60
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        max_age=max_age,
        expires=max_age,
        path="/",
    )

def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        path="/",
        samesite=COOKIE_SAMESITE,
        secure=COOKIE_SECURE,
    )

def create_token(username: str) -> str:
    payload = {
        "username": username,
        "exp": datetime.now(timezone.utc) + timedelta(days=TOKEN_EXPIRATION_DAYS),
        "iat": datetime.now(timezone.utc)
    }
    token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
    return token

@user_router.post("/login", response_model=LoginResponse)
def login(request: LoginRequest, response: Response):
    if request.username == ADMIN_USERNAME and request.password == ADMIN_PASSWORD:
        token = create_token(request.username)
        set_session_cookie(response, token)
        return {
            "access_token": token
        }
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Username or password is incorrect"
        )

@user_router.post("/logout")
def logout(response: Response):
    clear_session_cookie(response)
    return {"success": True}

@user_router.get("/user-info", response_model=UserInfoResponse)
def user_info(request: Request):
    username = get_current_username(request)
    return {"username": username}
