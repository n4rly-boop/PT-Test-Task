from __future__ import annotations

from typing import Sequence

from langchain_core.tools import tool
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import rag_models
from app.db.database import SessionLocal
from app.services.embedding import embedding_service, clear_text

TOP_K = 3

def vector_search(session: Session, query_vector: Sequence[float], limit: int):
    """Run pgvector similarity search when available."""
    distance = rag_models.RagDocumentChunk.embedding.cosine_distance(query_vector)
    statement = (
        select(
            rag_models.RagDocumentChunk.content.label("chunk_content"),
            rag_models.RagDocumentChunk.chunk_index.label("chunk_index"),
            rag_models.RagDocument.title.label("title"),
            rag_models.RagDocument.source_url.label("url"),
            distance.label("distance"),
        )
        .join(rag_models.RagDocument, rag_models.RagDocument.id == rag_models.RagDocumentChunk.document_id)
        .order_by(distance)
        .limit(limit)
    )
    try:
        return session.execute(statement).mappings().all()
    except Exception as exc:
        return "Vector search error: " + str(exc)

def format_results(rows) -> str:
    formatted = []
    for idx, row in enumerate(rows, start=1):
        title = row.get("title") or "Untitled"
        url = row.get("url")
        snippet = (row.get("chunk_content") or "").strip()
        header = f"{idx}. {title}"
        if url:
            header += f" ({url})"
        distance = row.get("distance")
        if distance is not None:
            header += f" [score={distance:.3f}]"
        formatted.append(f"{header}\n{snippet}")
    return "\n\n".join(formatted)


@tool("rag")
def rag_tool(query: str, top_k: int = TOP_K) -> str:
    """
    Retrieve relevant documentation chunks for a user query.
    """
    query = (query or "").strip()
    query = clear_text(query)
    if not query:
        return "Please provide a query to search the documentation."

    try:
        with SessionLocal() as session:
            results = []
            query_vector = embedding_service.embed_documents(query)

            if query_vector and session.bind.dialect.name == "postgresql":
                results = vector_search(session, query_vector, top_k)

    except Exception as exc:
        return f"Retrieval error: {exc}"


    if not results:
        return "No relevant documentation found."
    
    return format_results(results)
