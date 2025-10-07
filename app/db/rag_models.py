from __future__ import annotations

from datetime import datetime
from typing import List

from sqlalchemy import DateTime, ForeignKey, Index, Integer, MetaData, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship, declarative_base
from sqlalchemy.sql import func

from app.core.config import settings
from pgvector.sqlalchemy import Vector  # type: ignore

from app.db.database import (
    RAG_SCHEMA,
    SQLALCHEMY_DATABASE_URL,
    _schema_for_backend,
)


rag_metadata = MetaData(schema=_schema_for_backend(SQLALCHEMY_DATABASE_URL, RAG_SCHEMA))
RAGBase = declarative_base(metadata=rag_metadata)


class RagDocument(RAGBase):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    source_id: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    source_url: Mapped[str] = mapped_column(String(2048))
    title: Mapped[str] = mapped_column(String(512))
    content: Mapped[str] = mapped_column(Text())
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), default=datetime.now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=datetime.now,
        onupdate=datetime.now,
    )

    chunks: Mapped[List[RagDocumentChunk]] = relationship(
        "RagDocumentChunk",
        back_populates="document",
        cascade="all, delete-orphan",
    )


class RagDocumentChunk(RAGBase):
    __tablename__ = "document_chunks"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(ForeignKey(f"{RagDocument.__tablename__}.id", ondelete="CASCADE"))
    chunk_index: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text())
    embedding: Mapped[List[float]] = mapped_column(Vector(settings.embedding_dim))

    document: Mapped[RagDocument] = relationship("RagDocument", back_populates="chunks")

    __table_args__ = (
        UniqueConstraint("document_id", "chunk_index", name="uq_document_chunk_idx"),
        Index("ix_document_chunks_document_id", "document_id"),
    )
