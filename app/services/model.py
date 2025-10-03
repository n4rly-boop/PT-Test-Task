from typing import List

from langchain_openai import ChatOpenAI
from langchain_core.messages import BaseMessage, AIMessage, SystemMessage
from app.core.config import settings


system_prompt = """
You are a helpful assistant that can answer questions and help with tasks.
"""

class Model:
    """OpenAI-compatible chat model wrapper with LangChain tool binding support"""

    def __init__(self) -> None:
        api_key = settings.llm_api_key
        base_url = settings.llm_base_url
        model_name = settings.llm_model
        if not api_key:
            raise ValueError("LLM_API_KEY is not set")
        if not model_name:
            raise ValueError("LLM_MODEL is not set")
        
        kwargs = {}
        if base_url:
            kwargs["base_url"] = base_url

        self.llm = ChatOpenAI(model=model_name, api_key=api_key, **kwargs)

    def with_tools(self, tools):
        """Return an LLM bound with tools"""
        return self.llm.bind_tools(tools)

    def invoke(self, messages: List[BaseMessage]) -> AIMessage:
        """Invoke the model with LangChain BaseMessage list, returning AIMessage."""
        return self.llm.invoke([SystemMessage(content=system_prompt)] + messages)