"""Persistent vector store for reference document search.

Embeddings are cached in SQLite so PDF parsing + API calls only happen once.
On subsequent startups, cached embeddings load in seconds.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import math
import sqlite3
from pathlib import Path

from openai import AsyncOpenAI

from app.config import settings
from app.rag.loader import load_all_documents

logger = logging.getLogger(__name__)

DB_PATH = Path("data/embeddings.db")

_client: AsyncOpenAI | None = None
_chunks: list[dict] = []  # {"id", "text", "source", "embedding"}
_loaded = False


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=settings.openai_api_key)
    return _client


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


async def _embed(texts: list[str]) -> list[list[float]]:
    """Get embeddings from OpenAI."""
    client = _get_client()
    response = await client.embeddings.create(
        model=settings.embedding_model,
        input=texts,
    )
    return [item.embedding for item in response.data]


def _file_hash(filepath: Path) -> str:
    """Quick hash based on file size + mtime (fast, avoids reading large files)."""
    stat = filepath.stat()
    return hashlib.md5(f"{stat.st_size}:{stat.st_mtime_ns}".encode()).hexdigest()


def _db_load_cached(current_hashes: dict[str, str]) -> tuple[list[dict], set[str]]:
    """Load cached embeddings from SQLite. All DB ops in one thread."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS embeddings (
            chunk_id TEXT PRIMARY KEY,
            source TEXT NOT NULL,
            text TEXT NOT NULL,
            embedding BLOB NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS file_hashes (
            filename TEXT PRIMARY KEY,
            hash TEXT NOT NULL
        )
    """)
    conn.commit()

    # Get DB file hashes
    rows = conn.execute("SELECT filename, hash FROM file_hashes").fetchall()
    db_hashes = {r[0]: r[1] for r in rows}

    # Clean up stale files
    for filename in list(db_hashes.keys()):
        if filename not in current_hashes:
            conn.execute("DELETE FROM embeddings WHERE source = ?", (filename,))
            conn.execute("DELETE FROM file_hashes WHERE filename = ?", (filename,))
            logger.info("Removed stale cache for: %s", filename)
    conn.commit()

    # Load cached chunks for unchanged files
    chunks = []
    cached_sources = set()
    for filename, hash_val in current_hashes.items():
        if filename in db_hashes and db_hashes[filename] == hash_val:
            cursor = conn.execute(
                "SELECT chunk_id, source, text, embedding FROM embeddings WHERE source = ?",
                (filename,)
            )
            for row in cursor:
                chunks.append({
                    "id": row[0],
                    "source": row[1],
                    "text": row[2],
                    "embedding": json.loads(row[3]),
                })
            cached_sources.add(filename)

    conn.close()
    return chunks, cached_sources


def _db_save_chunks(chunks: list[dict], file_hashes: dict[str, str]) -> None:
    """Save new embeddings to SQLite. All DB ops in one thread."""
    conn = sqlite3.connect(str(DB_PATH))

    sources_to_save = set()
    for chunk in chunks:
        sources_to_save.add(chunk["source"])
        conn.execute(
            "INSERT OR REPLACE INTO embeddings (chunk_id, source, text, embedding) VALUES (?, ?, ?, ?)",
            (chunk["id"], chunk["source"], chunk["text"], json.dumps(chunk["embedding"])),
        )

    for source in sources_to_save:
        if source in file_hashes:
            conn.execute(
                "INSERT OR REPLACE INTO file_hashes (filename, hash) VALUES (?, ?)",
                (source, file_hashes[source]),
            )

    conn.commit()
    conn.close()


async def init_store() -> int:
    """Load documents with caching. Returns chunk count."""
    global _chunks, _loaded

    facts_dir = Path("data/facts")
    if not facts_dir.exists():
        _loaded = True
        logger.info("No reference documents to load")
        return 0

    current_files = {}
    for f in sorted(facts_dir.rglob("*")):
        if f.is_file() and not f.name.startswith("."):
            rel_path = str(f.relative_to(facts_dir)).replace("\\", "/")
            current_files[rel_path] = _file_hash(f)

    if not current_files:
        _loaded = True
        return 0

    # Load from cache (all SQLite ops in one thread)
    cached_chunks, cached_sources = await asyncio.to_thread(
        _db_load_cached, current_files
    )
    logger.info("Loaded %d chunks from cache (%d files)", len(cached_chunks), len(cached_sources))

    # Identify new/changed files
    new_files = {f: h for f, h in current_files.items() if f not in cached_sources}

    new_chunks = []
    if new_files:
        logger.info("Processing %d new/changed files: %s", len(new_files), list(new_files.keys()))

        # Extract text (slow for large PDFs)
        all_docs = await asyncio.to_thread(load_all_documents)
        new_doc_chunks = [c for c in all_docs if c["source"] in new_files]
        logger.info("Extracted %d text chunks from new files", len(new_doc_chunks))

        if new_doc_chunks:
            # Batch embed via OpenAI API
            batch_size = 100
            all_embeddings = []
            for i in range(0, len(new_doc_chunks), batch_size):
                batch = [c["text"] for c in new_doc_chunks[i:i + batch_size]]
                embeddings = await _embed(batch)
                all_embeddings.extend(embeddings)
                logger.info("Embedded batch %d/%d",
                            i // batch_size + 1,
                            (len(new_doc_chunks) + batch_size - 1) // batch_size)

            for chunk, emb in zip(new_doc_chunks, all_embeddings):
                chunk["embedding"] = emb
                new_chunks.append(chunk)

            # Save to cache (all SQLite ops in one thread)
            await asyncio.to_thread(_db_save_chunks, new_chunks, current_files)
            logger.info("Saved %d new chunks to cache", len(new_chunks))

    _chunks = cached_chunks + new_chunks
    _loaded = True
    logger.info("Vector store ready: %d total chunks", len(_chunks))
    return len(_chunks)


async def search(query: str, top_k: int = 5) -> list[dict]:
    """Search reference documents for relevant chunks."""
    global _loaded

    if not _loaded:
        await init_store()

    if not _chunks:
        return []

    query_emb = (await _embed([query]))[0]

    scored = []
    for chunk in _chunks:
        score = _cosine_similarity(query_emb, chunk["embedding"])
        scored.append((score, chunk))

    scored.sort(key=lambda x: x[0], reverse=True)

    results = []
    for score, chunk in scored[:top_k]:
        if score < 0.2:
            break
        results.append({
            "text": chunk["text"],
            "source": chunk["source"],
            "score": round(score, 3),
        })

    return results
