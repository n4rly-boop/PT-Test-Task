from typing import Any, Dict, Optional, List

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    session_id: Optional[str] = None


class ChatResponse(BaseModel):
    reply: str
    tools: Optional[List[str]] = None
    meta: Optional[Dict[str, Any]] = None