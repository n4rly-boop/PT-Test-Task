from fastapi import APIRouter

from app.core.config import settings
from app.schemas.chat import ChatRequest, ChatResponse


router = APIRouter()


@router.get("/", tags=["root"])
def read_root():
    return {
        "app": settings.app_name,
        "message": "PT-LLM-Assistant API running",
    }


@router.get("/health", tags=["health"])
def health_check():
    return {
        "status": "ok",
    }


@router.post("/chat", tags=["chat"])
def chat(request: ChatRequest) -> ChatResponse:
    reply = "Hello, world!"
    tool = "none"
    meta = None
    return ChatResponse(reply=reply, tool=tool, meta=meta)