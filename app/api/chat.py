from __future__ import annotations

from typing import List
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db import models as db_models
from app.db.database import get_db
from app.schemas.chat import (
    CreateSessionRequest,
    CreateSessionResponse,
    ListSessionsResponse,
    SendMessageRequest,
    MessageRecord,
    MessageHistoryResponse,
    ChatResponse,
)
from app.services.agent import SuperAssistantAgent
from langchain_core.messages import ToolMessage


router = APIRouter(prefix="/chat", tags=["chat"])
agent_service = SuperAssistantAgent()


@router.post("/sessions", response_model=CreateSessionResponse)
async def create_session(payload: CreateSessionRequest, db: AsyncSession = Depends(get_db)):
    user = await db.get(db_models.User, payload.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    session_id = str(uuid4())
    session = db_models.ChatSession(id=session_id, user_id=user.id, title=payload.title)
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return CreateSessionResponse(id=session.id, user_id=session.user_id, title=session.title, created_at=session.created_at)


@router.get("/sessions/{user_id}", response_model=ListSessionsResponse)
async def list_sessions(user_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(db_models.ChatSession)
        .where(db_models.ChatSession.user_id == user_id, db_models.ChatSession.archived.is_(False))
        .order_by(
            db_models.ChatSession.last_message_at.desc().nullslast(),
            db_models.ChatSession.created_at.desc(),
        )
    )
    sessions = result.scalars().all()
    out = [
        {
            "id": s.id,
            "title": s.title,
            "created_at": s.created_at,
            "updated_at": s.updated_at,
            "last_message_at": s.last_message_at,
            "message_count": s.message_count,
        }
        for s in sessions
    ]
    return ListSessionsResponse(sessions=out)


@router.post("/sessions/{session_id}/messages", response_model=ChatResponse)
async def send_message(session_id: str, payload: SendMessageRequest, db: AsyncSession = Depends(get_db)):
    session = await db.get(db_models.ChatSession, session_id)
    if not session or session.archived:
        raise HTTPException(status_code=404, detail="Session not found")

    # Persist user message
    user_msg = db_models.ChatMessage(session_id=session_id, role="user", content=payload.message)
    db.add(user_msg)
    session.message_count = (session.message_count or 0) + 1
    session.last_message_at = user_msg.created_at
    await db.commit()
    await db.refresh(session)

    # Prepare conversation memory: last n messages in this session
    history = await _load_history(session_id, db)
    messages = [{"role": m.role, "content": m.content} for m in history]
    # Run assistant
    response = await agent_service.run(messages)
    reply = response["messages"][-1].content
    tools = [tool.name for tool in response["messages"] if isinstance(tool, ToolMessage)]

    # Persist assistant reply
    assistant_msg = db_models.ChatMessage(session_id=session_id, role="assistant", content=reply)
    if f"LLM error {settings.llm_error_code}" in assistant_msg.content:
        raise HTTPException(status_code=500, detail="LLM error")
    db.add(assistant_msg)
    session.message_count = (session.message_count or 0) + 1
    session.last_message_at = assistant_msg.created_at
    await db.commit()

    return ChatResponse(reply=reply, tools=tools, meta={"session_id": session_id})


@router.get("/sessions/{session_id}/messages", response_model=MessageHistoryResponse)
async def get_history(session_id: str, db: AsyncSession = Depends(get_db)):
    session = await db.get(db_models.ChatSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    msgs = await _load_history(session_id, db)
    records = [MessageRecord(id=m.id, role=m.role, content=m.content, created_at=m.created_at) for m in msgs]
    return MessageHistoryResponse(session_id=session_id, messages=records)


@router.delete("/sessions/{session_id}")
async def archive_session(session_id: str, db: AsyncSession = Depends(get_db)):
    session = await db.get(db_models.ChatSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    session.archived = True
    await db.commit()
    return {"ok": True}


async def _load_history(session_id: str, db: AsyncSession) -> List[db_models.ChatMessage]:
    result = await db.execute(
        select(db_models.ChatMessage)
        .where(db_models.ChatMessage.session_id == session_id)
        .order_by(db_models.ChatMessage.created_at.asc())
        .limit(settings.chat_history_length)
    )
    return result.scalars().all()

