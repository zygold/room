"""极简 session 鉴权（单用户/小团队） — Repository 重构版."""
import hashlib, secrets, time
from datetime import datetime

from fastapi import APIRouter, Request, Response, HTTPException
from pydantic import BaseModel

from repositories.users import UserRepository

router = APIRouter()
user_repo = UserRepository()

SESSIONS: dict[str, dict] = {}
SESSION_TTL = 12 * 3600  # 12h


def _hash_pw(password: str, salt: str) -> str:
    return hashlib.sha256((salt + password).encode()).hexdigest()


def _gc_sessions():
    now = time.time()
    expired = [t for t, s in SESSIONS.items() if now - s["created_at"] > SESSION_TTL]
    for t in expired:
        SESSIONS.pop(t, None)


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/login")
def login(body: LoginRequest, resp: Response):
    """用户名密码登录, 成功后 Set-Cookie token=..."""
    _gc_sessions()
    row = user_repo.get_by_username(body.username)
    if not row or not row["is_active"]:
        raise HTTPException(401, "用户名或密码错误")
    expected = _hash_pw(body.password, row["salt"])
    if expected != row["password_hash"]:
        raise HTTPException(401, "用户名或密码错误")
    user_repo.update_last_login(row["id"])

    token = secrets.token_urlsafe(32)
    SESSIONS[token] = {
        "user_id": row["id"],
        "username": row["username"],
        "role": row["role"] or "admin",
        "display_name": row["display_name"] or row["username"],
        "created_at": time.time(),
    }
    resp.set_cookie("token", token, httponly=False, samesite="lax")
    return {"ok": True, **SESSIONS[token]}


@router.get("/me")
def me(req: Request):
    """返回当前登录用户信息, 未登录返回 null."""
    token = req.cookies.get("token")
    if token and token in SESSIONS:
        _gc_sessions()
        s = SESSIONS[token]
        now = time.time()
        if now - s["created_at"] > SESSION_TTL:
            SESSIONS.pop(token, None)
            return {"user": None}
        return {"user": {"username": s["username"], "role": s["role"], "display_name": s["display_name"], "user_id": s["user_id"]}}
    return {"user": None}


@router.post("/logout")
def logout(req: Request, resp: Response):
    token = req.cookies.get("token")
    if token:
        SESSIONS.pop(token, None)
    resp.delete_cookie("token")
    return {"ok": True}


def require_auth(req: Request) -> dict:
    """FastAPI 依赖: 未登录抛 401, 已登录返回 session dict."""
    _gc_sessions()
    token = req.cookies.get("token")
    if not token or token not in SESSIONS:
        raise HTTPException(401, "未登录")
    return SESSIONS[token]


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str


@router.post("/change-password")
def change_password(body: ChangePasswordRequest, req: Request):
    """修改当前用户密码."""
    token = req.cookies.get("token")
    if not token or token not in SESSIONS:
        raise HTTPException(401, "未登录")
    s = SESSIONS[token]
    if len(body.new_password) < 6:
        raise HTTPException(400, "新密码至少 6 位")
    row = user_repo.get_by_username(s["username"])
    if not row:
        raise HTTPException(404, "用户不存在")
    expected = _hash_pw(body.old_password, row["salt"])
    if expected != row["password_hash"]:
        raise HTTPException(400, "旧密码错误")
    new_hash = _hash_pw(body.new_password, row["salt"])
    user_repo.update_password(s["username"], new_hash)
    return {"detail": "密码已更新"}
