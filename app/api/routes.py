from fastapi import APIRouter
from langchain_core.messages import ToolMessage

from app.core.config import settings
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.agent import SuperAssistantAgent


router = APIRouter()
agent_service = SuperAssistantAgent()


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
    messages = [{"role": "user", "content": request.message}]
    response = agent_service.run(messages)
    reply = response["messages"][-1].content
    tools = [tool.name for tool in response["messages"] if isinstance(tool, ToolMessage)]
    meta = {"session_id": request.session_id}
    return ChatResponse(reply=reply, tools=tools, meta=meta)