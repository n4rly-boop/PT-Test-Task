from typing import Any, Dict, Optional, List
from datetime import datetime

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    session_id: Optional[str] = None


class ChatResponse(BaseModel):
    reply: str
    tools: Optional[List[str]] = None
    meta: Optional[Dict[str, Any]] = None


class CreateSessionRequest(BaseModel):
    user_id: int = Field(..., ge=1)
    title: Optional[str] = None


class CreateSessionResponse(BaseModel):
    id: str
    user_id: int
    title: Optional[str] = None
    created_at: datetime


class ListSessionsResponse(BaseModel):
    sessions: List[Dict[str, Any]]


class SendMessageRequest(BaseModel):
    message: str = Field(..., min_length=1)
    use_tools: Optional[bool] = True


class MessageRecord(BaseModel):
    id: int
    role: str
    content: str
    created_at: datetime


class MessageHistoryResponse(BaseModel):
    session_id: str
    messages: List[MessageRecord]