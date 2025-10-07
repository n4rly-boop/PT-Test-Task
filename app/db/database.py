from __future__ import annotations

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
    from app.db import models

    if engine.dialect.name == "postgresql":
        with engine.begin() as conn:
            conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {USER_SCHEMA}"))
            conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {RAG_SCHEMA}"))
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))

    Base.metadata.create_all(bind=engine)
