"""FastAPI application entry point."""

from __future__ import annotations

import logging

from fastapi import FastAPI, WebSocket
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.config import settings
from app.api.routes import router
from app.api.ws import websocket_handler

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

app = FastAPI(title="전한길 토론용 FACT 체크")


@app.on_event("startup")
async def startup_load_rag():
    """Start loading reference documents in background (non-blocking)."""
    import asyncio
    from app.rag.store import init_store

    async def _load():
        try:
            count = await init_store()
            logging.getLogger(__name__).info("RAG store loaded: %d chunks", count)
        except Exception as e:
            logging.getLogger(__name__).warning("RAG store init failed: %s", e)

    asyncio.create_task(_load())


# REST API
app.include_router(router)

# WebSocket
@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    await websocket_handler(websocket)

# Serve frontend
app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")


def main():
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=True,
    )


if __name__ == "__main__":
    main()
