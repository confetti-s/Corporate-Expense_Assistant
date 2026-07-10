"""FastAPI 认证依赖"""
import hashlib
import uuid
from functools import lru_cache
from fastapi import Request, HTTPException

# 简单的内存会话存储 (生产环境应使用 Redis)
_sessions: dict[str, dict] = {}


def create_session(user: dict) -> str:
    token = uuid.uuid4().hex
    _sessions[token] = user
    return token


def get_session(token: str) -> dict | None:
    return _sessions.get(token)


def remove_session(token: str):
    _sessions.pop(token, None)


def get_current_user(request: Request) -> dict:
    token = request.cookies.get("session_token")
    if not token:
        raise HTTPException(status_code=401, detail="未登录")
    user = get_session(token)
    if not user:
        raise HTTPException(status_code=401, detail="会话已过期，请重新登录")
    return user
