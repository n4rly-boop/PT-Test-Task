from __future__ import annotations

import asyncio
from pathlib import Path
from typing import AsyncGenerator, Generator, Optional

from sqlalchemy import MetaData, create_engine, text
from sqlalchemy.engine.url import URL, make_url
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from app.core.config import settings


SQLALCHEMY_DATABASE_URL = settings.db_url
USER_SCHEMA = "users"
RAG_SCHEMA = "rag"


def _schema_for_backend(url: str, schema: str) -> Optional[str]:
    """Return schema if backend supports it; otherwise None."""
    try:
        backend = make_url(url).get_backend_name()
    except Exception:
        return None
    if backend == "postgresql":
        return schema
    return None

def _async_database_url(url: str) -> str:
    """Translate sync SQLAlchemy URL to its async equivalent when possible."""
    try:
        parsed: URL = make_url(url)
    except Exception:
        return url

    driver = parsed.drivername
    if driver.startswith("postgresql"):
        parsed = parsed.set(drivername="postgresql+asyncpg")
    elif driver.startswith("sqlite"):
        parsed = parsed.set(drivername="sqlite+aiosqlite")
    return parsed.render_as_string(hide_password=False)


ASYNC_SQLALCHEMY_DATABASE_URL = _async_database_url(SQLALCHEMY_DATABASE_URL)

# Maintain a synchronous engine for scripts/utilities that rely on it
if SQLALCHEMY_DATABASE_URL.startswith("sqlite"):
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL,
        pool_pre_ping=True,
        connect_args={"check_same_thread": False},
    )
else:
    engine = create_engine(SQLALCHEMY_DATABASE_URL, pool_pre_ping=True)

async_engine: AsyncEngine
if ASYNC_SQLALCHEMY_DATABASE_URL.startswith("sqlite"):
    async_engine = create_async_engine(
        ASYNC_SQLALCHEMY_DATABASE_URL,
        pool_pre_ping=True,
    )
else:
    async_engine = create_async_engine(ASYNC_SQLALCHEMY_DATABASE_URL, pool_pre_ping=True)


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

metadata = MetaData(schema=_schema_for_backend(SQLALCHEMY_DATABASE_URL, USER_SCHEMA))
Base = declarative_base(metadata=metadata)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session


def get_sync_db() -> Generator:
    """Retain sync dependency for scripts/tests that still need it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


async def init_db() -> None:
    # Import models so they are registered with Base before create_all
    from app.db import models, rag_models

    async with async_engine.begin() as conn:
        if conn.dialect.name == "postgresql":
            await conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {USER_SCHEMA}"))
            await conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {RAG_SCHEMA}"))
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))

        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(rag_models.RAGBase.metadata.create_all)

    try:
        await asyncio.to_thread(_bootstrap_rag_data, rag_models)
    except Exception as exc:
        print("Failed to initialize RAG data: %s", exc)


def _bootstrap_rag_data(rag_models) -> None:
    """Populate the RAG schema from local embeddings or source documents."""
    from scripts.upload_embeddings import load_csv_embeddings, upsert_document_from_csv

    project_root = Path(__file__).resolve().parents[2]
    embeddings_dir = project_root / "data" / "embeddings"
    docs_dir = project_root / "data" / "docs"

    csv_files = sorted(embeddings_dir.glob("*.csv")) if embeddings_dir.exists() else []
    if not csv_files:
        csv_files = _generate_embeddings_from_docs(docs_dir, embeddings_dir)

    if not csv_files:
        print("No embeddings or source documents found for RAG bootstrap.")
        return

    print("Bootstrapping RAG data from %d embedding file(s).", len(csv_files))
    with SessionLocal() as session:
        for csv_file in csv_files:
            embeddings = load_csv_embeddings(csv_file)
            if not embeddings:
                print("No embeddings found in %s; skipping.", csv_file)
                continue

            for record in embeddings:
                upsert_document_from_csv(session, record, rag_models)

    print("RAG bootstrap complete.")


def _generate_embeddings_from_docs(docs_dir: Path, embeddings_dir: Path) -> list[Path]:
    """Create embeddings from JSONL documents when CSV embeddings are absent."""
    if not docs_dir.exists():
        return []

    from scripts.embed_documents import (
        create_embeddings,
    )

    generated_files = create_embeddings(docs_dir, embeddings_dir)
    if not generated_files:
        print("Embedding generation produced no files from %s.", docs_dir)
    return generated_files
