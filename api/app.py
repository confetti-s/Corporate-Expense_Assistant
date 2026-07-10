"""FastAPI 主应用"""
import sys
import os

# 确保项目根目录在 path 中
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse, HTMLResponse
from jinja2 import Environment, FileSystemLoader
from api.routes.auth_routes import router as auth_router
from api.routes.chat_routes import router as chat_router
from api.routes.budget_routes import router as budget_router
from api.routes.progress_routes import router as progress_router
from api.routes.approval_routes import router as approval_router
from api.routes.upload_routes import router as upload_router
from api.auth import get_current_user

app = FastAPI(title="FinFlow Corp - 企业财务报销助手")

# 静态文件
app.mount("/static", StaticFiles(directory="static"), name="static")

# 上传文件目录
if os.path.exists("uploads"):
    app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

# Jinja2 环境 (手动创建以避免 Starlette cache 兼容问题)
_jinja_env = Environment(
    loader=FileSystemLoader(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "templates")),
    auto_reload=True,
    cache_size=0,
)


def render_template(request: Request, name: str, context: dict = None) -> HTMLResponse:
    """渲染 Jinja2 模板"""
    template = _jinja_env.get_template(name)
    ctx = {"request": request}
    if context:
        ctx.update(context)
    return HTMLResponse(template.render(**ctx))


# 注册 API 路由
app.include_router(auth_router)
app.include_router(chat_router)
app.include_router(budget_router)
app.include_router(progress_router)
app.include_router(approval_router)
app.include_router(upload_router)


# ========== 页面路由 ==========

@app.get("/")
async def root(request: Request):
    """首页重定向到登录页"""
    return RedirectResponse(url="/login")


@app.get("/login")
async def login_page(request: Request):
    """登录页面"""
    return render_template(request, "login.html")


@app.get("/chat")
async def chat_page(request: Request):
    """对话报销页面"""
    try:
        user = get_current_user(request)
        return render_template(request, "chat.html", {"user": user})
    except Exception:
        return RedirectResponse(url="/login")


@app.get("/budget")
async def budget_page(request: Request):
    """预算看板页面"""
    try:
        user = get_current_user(request)
        return render_template(request, "budget.html", {"user": user})
    except Exception:
        return RedirectResponse(url="/login")


@app.get("/progress")
async def progress_page(request: Request):
    """进度查询页面"""
    try:
        user = get_current_user(request)
        return render_template(request, "progress.html", {"user": user})
    except Exception:
        return RedirectResponse(url="/login")


@app.get("/approval")
async def approval_page(request: Request):
    """审批中心页面"""
    try:
        user = get_current_user(request)
        return render_template(request, "approval.html", {"user": user})
    except Exception:
        return RedirectResponse(url="/login")


# ========== 健康检查 ==========

@app.get("/api/health")
async def health_check():
    return {"status": "ok", "service": "FinFlow Corp API"}
