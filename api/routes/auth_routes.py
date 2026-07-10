"""认证相关 API 路由"""
from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel
from src.db.auth import authenticate_user, register_user
from api.auth import create_session, remove_session, get_current_user
from fastapi import Request

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    user_id: str
    password: str


class RegisterRequest(BaseModel):
    username: str
    password: str
    name: str
    email: str
    department_id: str
    role: str = "employee"


@router.post("/login")
def login(req: LoginRequest, response: Response):
    user, error = authenticate_user(req.user_id, req.password)
    if error:
        raise HTTPException(status_code=401, detail=error)
    token = create_session(user)
    response.set_cookie(
        key="session_token",
        value=token,
        httponly=True,
        max_age=86400,  # 24小时
        samesite="lax",
    )
    return {"success": True, "user": user}


@router.post("/register")
def register(req: RegisterRequest):
    result = register_user(
        username=req.username,
        password=req.password,
        name=req.name,
        email=req.email,
        department_id=req.department_id,
        role=req.role,
    )
    if "失败" in result or "已存在" in result or "不能为空" in result:
        raise HTTPException(status_code=400, detail=result)
    return {"success": True, "message": result}


@router.post("/logout")
def logout(response: Response, request: Request):
    token = request.cookies.get("session_token")
    if token:
        remove_session(token)
    response.delete_cookie("session_token")
    return {"success": True}


@router.get("/me")
def me(request: Request):
    try:
        user = get_current_user(request)
        return {"user": user}
    except Exception:
        return {"user": None}
