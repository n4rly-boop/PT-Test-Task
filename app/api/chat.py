from __future__ import annotations

from uuid import uuid4
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db import models as db_models
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
def create_session(payload: CreateSessionRequest, db: Session = Depends(get_db)):
    user = db.get(db_models.User, payload.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    session_id = str(uuid4())
    session = db_models.ChatSession(id=session_id, user_id=user.id, title=payload.title)
    db.add(session)
    db.commit()
    db.refresh(session)
    return CreateSessionResponse(id=session.id, user_id=session.user_id, title=session.title, created_at=session.created_at)


@router.get("/sessions/{user_id}", response_model=ListSessionsResponse)
def list_sessions(user_id: int, db: Session = Depends(get_db)):
    sessions = (
        db.query(db_models.ChatSession)
        .filter(db_models.ChatSession.user_id == user_id, db_models.ChatSession.archived == False)  # noqa: E712
        .order_by(db_models.ChatSession.last_message_at.desc().nullslast(), db_models.ChatSession.created_at.desc())
        .all()
    )
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
def send_message(session_id: str, payload: SendMessageRequest, db: Session = Depends(get_db)):
    session = db.get(db_models.ChatSession, session_id)
    if not session or session.archived:
        raise HTTPException(status_code=404, detail="Session not found")

    # Persist user message
    user_msg = db_models.ChatMessage(session_id=session_id, role="user", content=payload.message)
    db.add(user_msg)
    session.message_count = (session.message_count or 0) + 1
    session.last_message_at = user_msg.created_at
    db.commit()

    # Run assistant
    messages = [
        {"role": "user", "content": payload.message},
    ]
    response = agent_service.run(messages)
    reply = response["messages"][-1].content
    tools = [tool.name for tool in response["messages"] if isinstance(tool, ToolMessage)]

    # Persist assistant reply
    assistant_msg = db_models.ChatMessage(session_id=session_id, role="assistant", content=reply)
    db.add(assistant_msg)
    session.message_count = (session.message_count or 0) + 1
    session.last_message_at = assistant_msg.created_at
    db.commit()

    return ChatResponse(reply=reply, tools=tools, meta={"session_id": session_id})


@router.get("/sessions/{session_id}/messages", response_model=MessageHistoryResponse)
def get_history(session_id: str, db: Session = Depends(get_db)):
    session = db.get(db_models.ChatSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    msgs: List[db_models.ChatMessage] = (
        db.query(db_models.ChatMessage)
        .filter(db_models.ChatMessage.session_id == session_id)
        .order_by(db_models.ChatMessage.created_at.asc())
        .all()
    )
    records = [MessageRecord(id=m.id, role=m.role, content=m.content, created_at=m.created_at) for m in msgs]
    return MessageHistoryResponse(session_id=session_id, messages=records)


@router.delete("/sessions/{session_id}")
def archive_session(session_id: str, db: Session = Depends(get_db)):
    session = db.get(db_models.ChatSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    session.archived = True
    db.commit()
    return {"ok": True}


