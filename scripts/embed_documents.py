from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from langchain_text_splitters import RecursiveCharacterTextSplitter
from app.services.embedding import clear_text

CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create embeddings from parsed documentation and save to CSV.")
    parser.add_argument("--input-dir", type=Path, default=Path("data/docs"), help="Directory containing JSONL files with `url`, `title`, `text` fields")
    parser.add_argument("--output-dir", type=Path, default=Path("data/embeddings"), help="Directory to save embedding CSV files")
    return parser.parse_args()


def load_jsonl(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def process_document(
    embedder,
    splitter: RecursiveCharacterTextSplitter,
    record: dict[str, str],
) -> list[dict]:
    """Process a single document and return list of chunks with embeddings."""
    text_content = (record.get("text") or "").strip()
    if not text_content:
        return []

    source_id = record.get("url") or record.get("title") or str(hash(text_content))
    source_url = record.get("url") or ""
    title = record.get("title") or ""
    
    chunk_content = clear_text(text_content)

    chunks = [chunk.strip() for chunk in splitter.split_text(chunk_content) if chunk.strip()]
    if not chunks:
        return []

    embeddings = embedder.embed_documents(chunks)

    result = []
    for index, (chunk, vector) in enumerate(zip(chunks, embeddings)):
        result.append({
            "source_id": source_id,
            "source_url": source_url,
            "title": title,
            "document_content": text_content,
            "chunk_index": index,
            "chunk_content": chunk,
            "embedding": ",".join(map(str, vector)),  # CSV-friendly format
        })

    return result

def save_to_csv(data: list[dict], output_path: Path) -> None:
    """Save embedding data to CSV file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if not data:
        return

    fieldnames = list(data[0].keys())
    with output_path.open("w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(data)


def create_embeddings(input_dir: Path, output_dir: Path) -> list[Path]:
    """Generate embeddings from JSONL documents and persist them as CSVs."""
    from app.services.embedding import embedding_service

    if not input_dir.exists():
        return []

    jsonl_files = list(input_dir.glob("*.jsonl"))
    if not jsonl_files:
        return []

    splitter = RecursiveCharacterTextSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)
    generated_paths: list[Path] = []

    total_docs = 0
    total_chunks = 0

    for jsonl_file in jsonl_files:
        print(f"Processing {jsonl_file}...")

        docs = load_jsonl(jsonl_file)
        if not docs:
            print(f"No documents found in {jsonl_file}; skipping.")
            continue

        all_chunks = []
        for record in docs:
            chunks = process_document(embedding_service, splitter, record)
            all_chunks.extend(chunks)

        if not all_chunks:
            print(f"No chunks generated from {jsonl_file}; skipping.")
            continue

        output_dir.mkdir(parents=True, exist_ok=True)
        output_filename = f"{jsonl_file.stem}.csv"
        output_path = output_dir / output_filename
        save_to_csv(all_chunks, output_path)

        print(f"Processed {len(docs)} documents into {len(all_chunks)} chunks.")
        print(f"Saved embeddings to {output_path}")

        total_docs += len(docs)
        total_chunks += len(all_chunks)
        generated_paths.append(output_path)

    if total_docs:
        print(f"\nTotal: processed {total_docs} documents into {total_chunks} chunks across {len(jsonl_files)} files.")

    return generated_paths


def main() -> None:
    args = parse_args()

    if not args.input_dir.exists():
        raise SystemExit(f"Input directory {args.input_dir} not found")

    generated = create_embeddings(args.input_dir, args.output_dir)
    if not generated:
        print(f"No embeddings generated for {args.input_dir}")

if __name__ == "__main__":
    main()
