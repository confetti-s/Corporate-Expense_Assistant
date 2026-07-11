"""对话报销相关 API 路由"""
import asyncio
import time
import json
import uuid
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from src.db.database import SessionLocal
from src.db.models import ChatHistory
from api.auth import get_current_user

router = APIRouter(prefix="/api/chat", tags=["chat"])


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None


class ChatContextRequest(BaseModel):
    content: str
    role: str = "assistant"
    session_id: Optional[str] = None


@router.post("/send")
async def send_message(req: ChatRequest, user: dict = Depends(get_current_user)):
    """发送消息给AI Agent并获取流式响应"""
    from src.agent.expense_agent import run_agent

    session_id = req.session_id or uuid.uuid4().hex

    # 保存用户消息到历史
    db = SessionLocal()
    try:
        db.add(ChatHistory(
            user_id=user["user_id"],
            session_id=session_id,
            role="user",
            content=req.message,
        ))
        db.commit()
    finally:
        db.close()

    # 加载历史对话，构建 Agent 上下文记忆
    db2 = SessionLocal()
    chat_history = []
    try:
        history_records = (
            db2.query(ChatHistory)
            .filter_by(user_id=user["user_id"], session_id=session_id)
            .order_by(ChatHistory.created_at.asc())
            .limit(20)
            .all()
        )
        for m in history_records:
            chat_history.append({"role": m.role, "content": m.content})
    finally:
        db2.close()

    # 构建带用户上下文的查询
    enriched_query = f"[当前用户: {user['name']}({user['user_id']}), 部门: {user.get('department_id', 'N/A')}, 角色: {user['role']}]\n{req.message}"

    async def generate():
        full_response = ""
        try:
            buf = ""
            last_flush = time.monotonic()
            for chunk in run_agent(enriched_query, chat_history=chat_history):
                full_response += chunk
                buf += chunk
                now = time.monotonic()
                if buf and (now - last_flush >= 0.08 or len(buf) >= 15):
                    yield f"data: {json.dumps({'chunk': buf})}\n\n"
                    buf = ""
                    last_flush = now
                    await asyncio.sleep(0)
            if buf:
                yield f"data: {json.dumps({'chunk': buf})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
        finally:
            # 保存AI响应到历史
            db2 = SessionLocal()
            try:
                db2.add(ChatHistory(
                    user_id=user["user_id"],
                    session_id=session_id,
                    role="assistant",
                    content=full_response,
                ))
                db2.commit()
            finally:
                db2.close()
            yield f"data: {json.dumps({'session_id': session_id, 'done': True})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


@router.post("/context")
async def save_context(req: ChatContextRequest, user: dict = Depends(get_current_user)):
    """保存上下文消息到聊天历史（不触发AI响应），用于OCR结果等"""
    session_id = req.session_id or uuid.uuid4().hex
    db = SessionLocal()
    try:
        db.add(ChatHistory(
            user_id=user["user_id"],
            session_id=session_id,
            role=req.role,
            content=req.content,
        ))
        db.commit()
        return {"success": True, "session_id": session_id}
    finally:
        db.close()


@router.get("/history")
def get_chat_history(
    user: dict = Depends(get_current_user),
    session_id: str = None,
    limit: int = 50,
):
    db = SessionLocal()
    try:
        query = db.query(ChatHistory).filter_by(user_id=user["user_id"])
        if session_id:
            query = query.filter_by(session_id=session_id)
        messages = query.order_by(ChatHistory.created_at.desc()).limit(limit).all()
        return {
            "messages": [{
                "role": m.role,
                "content": m.content,
                "session_id": m.session_id,
                "created_at": m.created_at.strftime('%Y-%m-%d %H:%M:%S') if m.created_at else "",
            } for m in reversed(messages)]
        }
    finally:
        db.close()


@router.get("/sessions")
def get_chat_sessions(user: dict = Depends(get_current_user)):
    db = SessionLocal()
    try:
        from sqlalchemy import distinct, func
        sessions = db.query(
            ChatHistory.session_id,
            func.min(ChatHistory.created_at).label('first_msg'),
            func.count(ChatHistory.id).label('msg_count'),
        ).filter_by(user_id=user["user_id"]).group_by(ChatHistory.session_id).order_by(
            func.min(ChatHistory.created_at).desc()
        ).limit(20).all()
        return {
            "sessions": [{
                "session_id": s.session_id,
                "first_message_at": s.first_msg.strftime('%Y-%m-%d %H:%M:%S') if s.first_msg else "",
                "message_count": s.msg_count,
            } for s in sessions]
        }
    finally:
        db.close()
