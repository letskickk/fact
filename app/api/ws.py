"""WebSocket handler for real-time fact-check streaming."""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid

from fastapi import WebSocket, WebSocketDisconnect

from app.capture.stream import capture_audio_chunks
from app.stt.whisper import transcribe
from app.stt.refiner import refine
from app.checker.classifier import classify
from app.checker.verifier import verify
from app.models.schemas import Statement
from app.rag.store import search as rag_search

logger = logging.getLogger(__name__)

# Active sessions: session_id -> cancel event
_sessions: dict[str, asyncio.Event] = {}


async def _send(ws: WebSocket, event_type: str, data: dict) -> None:
    """Send a JSON event over WebSocket."""
    try:
        await ws.send_json({"type": event_type, "data": data})
    except Exception:
        pass


async def _run_pipeline(ws: WebSocket, session_id: str, youtube_url: str) -> None:
    """Run the full capture → STT → classify → verify pipeline."""
    stop_event = _sessions[session_id]

    await _send(ws, "status", {"session_id": session_id, "status": "running"})

    chunk_count = 0
    start_time = time.time()

    try:
        async for audio_path in capture_audio_chunks(youtube_url):
            if stop_event.is_set():
                break

            chunk_count += 1
            elapsed = time.time() - start_time

            # Step 1: STT
            raw_text = await transcribe(audio_path)
            if not raw_text:
                continue

            # Step 1.5: LLM 텍스트 보정
            text = await refine(raw_text)

            statement = Statement(
                text=text,
                timestamp=elapsed,
            )

            await _send(ws, "transcription", {
                "id": statement.id,
                "text": statement.text,
                "timestamp": statement.timestamp,
            })

            # Step 2: Classify
            classification = await classify(statement.id, statement.text)

            await _send(ws, "classification", {
                "statement_id": statement.id,
                "needs_check": classification.needs_check,
                "claim_type": classification.claim_type.value,
                "reason": classification.reason,
            })

            if not classification.needs_check:
                continue

            # Step 3: Search reference documents (RAG)
            context = None
            try:
                rag_results = await rag_search(statement.text, top_k=3)
                if rag_results:
                    context_parts = []
                    for r in rag_results:
                        context_parts.append(f"[{r['source']}] {r['text']}")
                    context = "\n\n".join(context_parts)
                    logger.info("RAG found %d relevant chunks for [%s]",
                                len(rag_results), statement.id)
            except Exception as e:
                logger.warning("RAG search failed: %s", e)

            # Step 4: Verify (with web search + reference context)
            result = await verify(statement.id, statement.text, context=context)

            await _send(ws, "fact_check", {
                "statement_id": result.statement_id,
                "statement_text": result.statement_text,
                "verdict": result.verdict.value,
                "confidence": result.confidence,
                "explanation": result.explanation,
                "source_type": result.source_type,
                "sources": result.sources,
            })

            # Clean up temp audio file
            try:
                audio_path.unlink(missing_ok=True)
            except OSError:
                pass

    except asyncio.CancelledError:
        logger.info("Pipeline cancelled for session %s", session_id)
    except Exception as e:
        logger.exception("Pipeline error for session %s", session_id)
        await _send(ws, "error", {"message": str(e)})
    finally:
        await _send(ws, "status", {
            "session_id": session_id,
            "status": "stopped",
            "chunks_processed": chunk_count,
        })


async def websocket_handler(ws: WebSocket) -> None:
    """Handle a WebSocket connection for live fact-checking."""
    await ws.accept()
    session_id = uuid.uuid4().hex[:8]
    logger.info("WebSocket connected: session=%s", session_id)

    pipeline_task: asyncio.Task | None = None

    try:
        while True:
            data = await ws.receive_json()
            action = data.get("action")

            if action == "start":
                youtube_url = data.get("youtube_url", "")
                if not youtube_url:
                    await _send(ws, "error", {"message": "youtube_url is required"})
                    continue

                # Stop existing pipeline if running
                if pipeline_task and not pipeline_task.done():
                    _sessions[session_id].set()
                    pipeline_task.cancel()

                _sessions[session_id] = asyncio.Event()
                pipeline_task = asyncio.create_task(
                    _run_pipeline(ws, session_id, youtube_url)
                )
                logger.info("Pipeline started: session=%s, url=%s", session_id, youtube_url)

            elif action == "stop":
                if session_id in _sessions:
                    _sessions[session_id].set()
                if pipeline_task and not pipeline_task.done():
                    pipeline_task.cancel()
                logger.info("Pipeline stop requested: session=%s", session_id)

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected: session=%s", session_id)
    finally:
        if session_id in _sessions:
            _sessions[session_id].set()
        if pipeline_task and not pipeline_task.done():
            pipeline_task.cancel()
        _sessions.pop(session_id, None)
