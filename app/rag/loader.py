"""Load reference files (PDF/TXT) into text chunks for RAG."""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

FACTS_DIR = Path("data/facts")
CHUNK_SIZE = 800  # characters per chunk
CHUNK_OVERLAP = 200  # overlap between chunks


def _extract_pdf_text(path: Path) -> str:
    """Extract all text from a PDF file using pypdf."""
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    texts = []
    for page in reader.pages:
        text = page.extract_text()
        if text:
            texts.append(text)
    return "\n".join(texts)


def _extract_txt_text(path: Path) -> str:
    """Read a plain text file."""
    return path.read_text(encoding="utf-8", errors="replace")


def _chunk_text(text: str, source: str) -> list[dict]:
    """Split text into overlapping chunks with metadata."""
    chunks = []
    # Clean up whitespace
    text = " ".join(text.split())
    if not text:
        return chunks

    start = 0
    idx = 0
    while start < len(text):
        end = start + CHUNK_SIZE
        chunk_text = text[start:end]
        if chunk_text.strip():
            chunks.append({
                "id": f"{source}_{idx}",
                "text": chunk_text.strip(),
                "source": source,
            })
            idx += 1
        start += CHUNK_SIZE - CHUNK_OVERLAP

    return chunks


def load_all_documents() -> list[dict]:
    """Load all documents from data/facts/ and return text chunks.

    Returns list of {"id": str, "text": str, "source": str}.
    """
    if not FACTS_DIR.exists():
        logger.info("No facts directory found at %s", FACTS_DIR)
        return []

    all_chunks = []
    for f in sorted(FACTS_DIR.rglob("*")):
        if f.name.startswith(".") or not f.is_file():
            continue

        try:
            if f.suffix.lower() == ".pdf":
                text = _extract_pdf_text(f)
            elif f.suffix.lower() in (".txt", ".md", ".csv"):
                text = _extract_txt_text(f)
            else:
                logger.info("Skipping unsupported file: %s", f.name)
                continue

            # 하위폴더 경로 포함한 소스명
            rel_path = f.relative_to(FACTS_DIR)
            source_name = str(rel_path).replace("\\", "/")
            chunks = _chunk_text(text, source_name)
            all_chunks.extend(chunks)
            logger.info("Loaded %s: %d chunks (%d chars)", source_name, len(chunks), len(text))

        except Exception as e:
            logger.warning("Failed to load %s: %s", f.name, e)

    logger.info("Total reference chunks: %d", len(all_chunks))
    return all_chunks
