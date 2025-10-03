from __future__ import annotations

import os
from typing import Dict, List

from typing_extensions import Annotated

from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.tools import tool
from app.services.model import Model
from app.core.config import settings


class State(dict):
    messages: Annotated[List[BaseMessage], add_messages]


@tool("rag")
def rag_tool(query: str) -> str:
    """ Get information from documentation """
    print(f"RAG: {query}")
    return "[RAG:mock]"


@tool("sql")
def sql_tool(query: str) -> str:
    """ Get information from database """
    print(f"SQL: {query}")
    return "[SQL:mock]"


@tool("web")
def web_tool(query: str) -> str:
    """ Get information from web """
    print(f"WEB: {query}")
    return "[WEB:mock]"


TOOLS = [rag_tool, sql_tool, web_tool]

def chatbot(state: State) -> Dict[str, List[BaseMessage]]:
    try:
        llm = Model().with_tools(TOOLS)
        ai_message = llm.invoke(state["messages"])
    except Exception as e:
        return {"messages": [AIMessage(content=f"LLM error {settings.llm_error_code}: {e}")]}
    return {"messages": [ai_message]}

def route_tools(state: State) -> str:
    try:
        ai_message = state[-1] if isinstance(state, list) else state["messages"][-1]
        if hasattr(ai_message, "tool_calls") and len(ai_message.tool_calls) > 0:
            return "tools"
        return END
    except Exception:
        raise ValueError(f"No messages found in input state to tool_edge: {state}")
    

class SuperAssistantAgent:
    def __init__(self) -> None:
        graph = StateGraph(State)
        graph.add_node("chatbot", chatbot)
        graph.add_node("tools", ToolNode(tools=TOOLS))

        graph.add_conditional_edges("chatbot", route_tools)
        graph.add_edge("tools", "chatbot")
        graph.set_entry_point("chatbot")
        self.graph = graph.compile()

    def run(self, messages: List[BaseMessage]) -> AIMessage:
        response = self.graph.invoke({"messages": messages})
        return response