from __future__ import annotations

import argparse
import csv
import os
import sys
from pathlib import Path

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import delete, text
from sqlalchemy.orm import Session


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Upload embeddings from CSV files to PostgreSQL with pgvector.")
    parser.add_argument("--input-dir", type=Path, default=Path("data/embeddings"), help="Directory containing embedding CSV files")
    parser.add_argument("--pattern", type=str, default="*.csv", help="File pattern to match (default: *.csv)")
    parser.add_argument("--db-url", type=str, default="postgresql+psycopg://postgres:postgres@localhost:5432/db", help="Override DATABASE_URL before importing app modules")
    return parser.parse_args()


def ensure_pgvector(conn) -> None:
    if conn.dialect.name == "postgresql":
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))


def load_csv_embeddings(csv_path: Path) -> list[dict]:
    """Load embeddings from CSV file."""
    embeddings = []
    with csv_path.open("r", encoding="utf-8") as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            # Convert embedding string back to list of floats
            embedding_str = row.get("embedding", "")
            if embedding_str:
                try:
                    embedding = [float(x) for x in embedding_str.split(",")]
                    row["embedding"] = embedding
                except ValueError:
                    print(f"Warning: Invalid embedding format in {csv_path}, skipping row")
                    continue
            embeddings.append(row)
    return embeddings


def upsert_document_from_csv(
    session: Session,
    record: dict,
    models,
) -> None:
    """Upsert document and chunks from CSV record."""
    source_id = record["source_id"]
    source_url = record["source_url"]
    title = record["title"]
    document_content = record["document_content"]
    chunk_index = int(record["chunk_index"])
    chunk_content = record["chunk_content"]
    embedding = record["embedding"]

    # Find or create document
    document = session.query(models.RagDocument).filter_by(source_id=source_id).first()
    if not document:
        document = models.RagDocument(
            source_id=source_id,
            source_url=source_url,
            title=title,
            content=document_content,
        )
        session.add(document)
        session.flush()

    # Delete existing chunk if it exists
    session.execute(
        delete(models.RagDocumentChunk).where(
            models.RagDocumentChunk.document_id == document.id,
            models.RagDocumentChunk.chunk_index == chunk_index
        )
    )

    # Add new chunk
    chunk = models.RagDocumentChunk(
        document_id=document.id,
        chunk_index=chunk_index,
        content=chunk_content,
        embedding=embedding,
    )
    session.add(chunk)
    session.commit()


def main() -> None:
    args = parse_args()

    # Override DATABASE_URL before importing app modules
    if args.db_url:
        os.environ["DATABASE_URL"] = args.db_url

    # Import app modules after DATABASE_URL is set
    from app.db.database import SessionLocal, engine, init_db
    from app.db import rag_models

    if not args.input_dir.exists():
        raise SystemExit(f"Input directory {args.input_dir} not found")

    # Find all matching files in the directory
    csv_files = list(args.input_dir.glob(args.pattern))
    if not csv_files:
        print(f"No files matching '{args.pattern}' found in {args.input_dir}")
        return

    init_db()
    with engine.begin() as conn:
        ensure_pgvector(conn)
    rag_models.RAGBase.metadata.create_all(bind=engine)

    total_chunks = 0
    with SessionLocal() as session:
        for csv_file in csv_files:
            print(f"Processing {csv_file}...")
            embeddings = load_csv_embeddings(csv_file)
            for record in embeddings:
                upsert_document_from_csv(session, record, rag_models)
            print(f"Uploaded {len(embeddings)} chunks from {csv_file}")
            total_chunks += len(embeddings)

    print(f"Successfully uploaded {total_chunks} chunks from {len(csv_files)} files to the database.")


if __name__ == "__main__":
    main()
