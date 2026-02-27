"""WebSocket handler for real-time fact-check streaming."""

from __future__ import annotations

import asyncio
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

# Keepalive interval (seconds)
_PING_INTERVAL = 20


async def _send(ws: WebSocket, event_type: str, data: dict) -> bool:
    """Send a JSON event over WebSocket. Returns False if connection is dead."""
    try:
        await ws.send_json({"type": event_type, "data": data})
        return True
    except Exception:
        return False


async def _keepalive(ws: WebSocket, stop_event: asyncio.Event) -> None:
    """Send periodic ping to keep WebSocket alive through proxies."""
    while not stop_event.is_set():
        try:
            await asyncio.sleep(_PING_INTERVAL)
            if stop_event.is_set():
                break
            await ws.send_json({"type": "ping", "data": {"ts": time.time()}})
        except Exception:
            break


async def _run_pipeline(ws: WebSocket, session_id: str, youtube_url: str) -> None:
    """Run the full capture → STT → classify → verify pipeline."""
    stop_event = _sessions[session_id]

    await _send(ws, "status", {"session_id": session_id, "status": "running"})

    chunk_count = 0
    error_count = 0
    start_time = time.time()

    try:
        async for audio_path in capture_audio_chunks(youtube_url):
            if stop_event.is_set():
                break

            chunk_count += 1
            elapsed = time.time() - start_time

            try:
                # Step 1: STT (timeout 30s)
                raw_text = await asyncio.wait_for(transcribe(audio_path), timeout=30)
                if not raw_text:
                    continue

                # Step 1.5: LLM 텍스트 보정 (timeout 15s)
                try:
                    text = await asyncio.wait_for(refine(raw_text), timeout=15)
                except (asyncio.TimeoutError, Exception):
                    text = raw_text

                statement = Statement(
                    text=text,
                    timestamp=elapsed,
                )

                if not await _send(ws, "transcription", {
                    "id": statement.id,
                    "text": statement.text,
                    "timestamp": statement.timestamp,
                }):
                    logger.warning("WebSocket send failed, stopping pipeline")
                    break

                # Step 2: Classify (timeout 15s)
                classification = await asyncio.wait_for(
                    classify(statement.id, statement.text), timeout=15
                )

                await _send(ws, "classification", {
                    "statement_id": statement.id,
                    "needs_check": classification.needs_check,
                    "claim_type": classification.claim_type.value,
                    "reason": classification.reason,
                })

                if not classification.needs_check:
                    error_count = 0
                    continue

                # Step 3: Search reference documents (RAG) (timeout 10s)
                context = None
                try:
                    rag_results = await asyncio.wait_for(
                        rag_search(statement.text, top_k=3), timeout=10
                    )
                    if rag_results:
                        context_parts = []
                        for r in rag_results:
                            context_parts.append(f"[{r['source']}] {r['text']}")
                        context = "\n\n".join(context_parts)
                        logger.info("RAG found %d relevant chunks for [%s]",
                                    len(rag_results), statement.id)
                except (asyncio.TimeoutError, Exception) as e:
                    logger.warning("RAG search failed: %s", e)

                # Step 4: Verify (timeout 60s — web search can be slow)
                result = await asyncio.wait_for(
                    verify(statement.id, statement.text, context=context),
                    timeout=60,
                )

                await _send(ws, "fact_check", {
                    "statement_id": result.statement_id,
                    "statement_text": result.statement_text,
                    "verdict": result.verdict.value,
                    "confidence": result.confidence,
                    "explanation": result.explanation,
                    "source_type": result.source_type,
                    "sources": result.sources,
                })

                error_count = 0

            except asyncio.TimeoutError:
                logger.warning("Chunk %d: API timeout, skipping", chunk_count)
                error_count += 1
                await _send(ws, "error", {"message": f"API 타임아웃 (청크 {chunk_count}), 계속 진행..."})
            except Exception as e:
                logger.warning("Chunk %d processing error: %s", chunk_count, e)
                error_count += 1
                await _send(ws, "error", {"message": f"처리 오류: {str(e)[:100]}, 계속 진행..."})
            finally:
                # Clean up temp audio file
                try:
                    audio_path.unlink(missing_ok=True)
                except OSError:
                    pass

            # 연속 에러 10회 시 중지
            if error_count >= 10:
                logger.error("10 consecutive errors, stopping pipeline")
                await _send(ws, "error", {"message": "연속 에러 10회로 파이프라인 중지"})
                break

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
    keepalive_stop = asyncio.Event()
    keepalive_task = asyncio.create_task(_keepalive(ws, keepalive_stop))

    try:
        while True:
            # receive_json with timeout to detect dead connections
            try:
                data = await asyncio.wait_for(ws.receive_json(), timeout=300)
            except asyncio.TimeoutError:
                # 5분 동안 클라이언트 메시지 없으면 — 정상 (파이프라인이 알아서 보냄)
                continue

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
                    try:
                        await pipeline_task
                    except (asyncio.CancelledError, Exception):
                        pass

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

            elif action == "pong":
                pass  # client responded to ping — connection alive

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected: session=%s", session_id)
    except Exception as e:
        logger.warning("WebSocket handler error: session=%s, %s", session_id, e)
    finally:
        keepalive_stop.set()
        keepalive_task.cancel()
        if session_id in _sessions:
            _sessions[session_id].set()
        if pipeline_task and not pipeline_task.done():
            pipeline_task.cancel()
        _sessions.pop(session_id, None)
