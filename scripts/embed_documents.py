from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import nltk
from langchain_text_splitters import RecursiveCharacterTextSplitter

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

def clear_text(text: str) -> str:
    #TODO add lemmatization/stemming for russian words
    text = ''.join(c for c in text if c.isprintable() or c in '\n\r\t ')
    lowered = text.lower()
    normalized = re.sub(r"[^а-яА-Яa-zA-Z0-9\s]+", " ", lowered)
    removed_spaces = re.sub(r"\s+", " ", normalized)
    stopwords = nltk.corpus.stopwords.words("russian")
    cleared_tokens = [token for token in removed_spaces.split() if token not in stopwords]
    return " ".join(cleared_tokens)

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


def main() -> None:
    args = parse_args()

    from app.services.embedding import EmbeddingService

    if not args.input_dir.exists():
        raise SystemExit(f"Input directory {args.input_dir} not found")

    # Find all JSONL files in the input directory
    jsonl_files = list(args.input_dir.glob("*.jsonl"))
    if not jsonl_files:
        print(f"No JSONL files found in {args.input_dir}")
        return

    splitter = RecursiveCharacterTextSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)
    embedder = EmbeddingService()

    total_docs = 0
    total_chunks = 0

    # Process each JSONL file
    for jsonl_file in jsonl_files:
        print(f"Processing {jsonl_file}...")

        docs = load_jsonl(jsonl_file)
        if not docs:
            print(f"No documents found in {jsonl_file}; skipping.")
            continue

        # Process all documents in this file
        all_chunks = []
        for record in docs:
            chunks = process_document(embedder, splitter, record)
            all_chunks.extend(chunks)

        if not all_chunks:
            print(f"No chunks generated from {jsonl_file}; skipping.")
            continue

        # Save to CSV with original filename
        output_filename = f"{jsonl_file.stem}.csv"
        output_path = args.output_dir / output_filename
        save_to_csv(all_chunks, output_path)

        print(f"Processed {len(docs)} documents into {len(all_chunks)} chunks.")
        print(f"Saved embeddings to {output_path}")

        total_docs += len(docs)
        total_chunks += len(all_chunks)

    print(f"\nTotal: processed {total_docs} documents into {total_chunks} chunks across {len(jsonl_files)} files.")

if __name__ == "__main__":
    main()