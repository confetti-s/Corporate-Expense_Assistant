"""对话报销相关 API 路由"""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from typing import Optional
from pydantic import BaseModel
from src.db.database import SessionLocal
from src.db.models import ChatHistory
from api.auth import get_current_user
from datetime import datetime
import uuid
import json

router = APIRouter(prefix="/api/chat", tags=["chat"])


class ChatRequest(BaseModel):
    message: str
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

    # 构建带用户上下文的查询
    enriched_query = f"[当前用户: {user['name']}({user['user_id']}), 部门: {user.get('department_id', 'N/A')}, 角色: {user['role']}]\n{req.message}"

    async def generate():
        full_response = ""
        try:
            for char in run_agent(enriched_query):
                full_response += char
                yield f"data: {json.dumps({'chunk': char})}\n\n"
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
