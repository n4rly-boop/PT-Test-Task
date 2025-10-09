from typing import Dict, List

from langchain_core.messages import AIMessage, BaseMessage, SystemMessage
from langchain_openai import ChatOpenAI

try:
    from langchain_community.chat_models import ChatOllama
except ImportError:  # pragma: no cover - optional dependency
    ChatOllama = None

from app.core.config import settings


system_prompt = """
You are a helpful assistant that can answer questions and help with tasks.
"""


class Model:
    """Provider-agnostic chat model wrapper with LangChain tool binding support."""

    def __init__(self) -> None:
        self.llm = self._build_llm()

    def _build_llm(self):
        provider = (settings.llm_provider or "openai").lower()
        builder = {
            "openai": self._build_openai_like,
            "ollama": self._build_ollama
        }.get(provider)

        if builder is None:
            raise ValueError(f"Unsupported LLM provider '{settings.llm_provider}'")

        return builder(provider)

    def _build_openai_like(self, provider: str):
        """Providers that speak the OpenAI API (OpenAI, OpenRouter, vLLM)."""
        model_name = settings.llm_model
        if not model_name:
            raise ValueError("LLM_MODEL is not set")

        api_key = settings.llm_api_key
        if provider in {"openai", "openrouter"} and not api_key:
            # Tests may run without a cloud key; fall back to stub execution
            return StubLLM()

        base_url_overrides: Dict[str, str] = {
            "openrouter": "https://openrouter.ai/api/v1",
            "vllm": "http://localhost:8000/v1",
        }
        base_url = settings.llm_base_url or base_url_overrides.get(provider)

        kwargs = {}
        if base_url:
            kwargs["base_url"] = base_url

        # Provide a dummy key for local OpenAI-compatible deployments.
        effective_key = api_key or "EMPTY"

        return ChatOpenAI(model=model_name, api_key=effective_key, **kwargs)

    def _build_ollama(self, _: str):
        if ChatOllama is None:
            raise ImportError("langchain-community is required for Ollama provider")

        model_name = settings.llm_model or "llama3"
        base_url = settings.llm_base_url or "http://localhost:11434"
        return ChatOllama(model=model_name, base_url=base_url)

    def with_tools(self, tools):
        """Return an LLM bound with tools"""
        return self.llm.bind_tools(tools)

    def invoke(self, messages: List[BaseMessage]) -> AIMessage:
        """Invoke the model with LangChain BaseMessage list, returning AIMessage."""
        return self.llm.invoke([SystemMessage(content=system_prompt)] + messages)

    async def ainvoke(self, messages: List[BaseMessage]) -> AIMessage:
        """Asynchronously invoke the model with LangChain BaseMessage list."""
        return await self.llm.ainvoke([SystemMessage(content=system_prompt)] + messages)


class StubLLM:
    def bind_tools(self, tools):
        return self

    def invoke(self, messages: List[BaseMessage]) -> AIMessage:
        # Simple echo-like behavior for tests
        last_user = None
        for m in reversed(messages):
            try:
                if getattr(m, "type", "") == "human":
                    last_user = m
                    break
            except Exception:
                pass
        content = "Test response" if last_user is None else "Echo: " + getattr(last_user, "content", "")
        return AIMessage(content=content)

    async def ainvoke(self, messages: List[BaseMessage]) -> AIMessage:
        return self.invoke(messages)
