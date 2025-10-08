from __future__ import annotations

from pathlib import Path
from typing import Generator, Optional

from sqlalchemy import MetaData, create_engine, text
from sqlalchemy.engine.url import make_url
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

# Use a synchronous engine; FastAPI endpoints are sync right now
if SQLALCHEMY_DATABASE_URL.startswith("sqlite"):
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL,
        pool_pre_ping=True,
        connect_args={"check_same_thread": False},
    )
else:
    engine = create_engine(SQLALCHEMY_DATABASE_URL, pool_pre_ping=True)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

metadata = MetaData(schema=_schema_for_backend(SQLALCHEMY_DATABASE_URL, USER_SCHEMA))
Base = declarative_base(metadata=metadata)


def get_db() -> Generator:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    # Import models so they are registered with Base before create_all
    from app.db import models, rag_models

    if engine.dialect.name == "postgresql":
        with engine.begin() as conn:
            conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {USER_SCHEMA}"))
            conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {RAG_SCHEMA}"))
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))

    Base.metadata.create_all(bind=engine)
    rag_models.RAGBase.metadata.create_all(bind=engine)

    try:
        _bootstrap_rag_data(rag_models)
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
