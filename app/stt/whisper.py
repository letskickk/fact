"""Speech-to-text using OpenAI Whisper API."""

from __future__ import annotations

import logging
from pathlib import Path

from openai import AsyncOpenAI

from app.config import settings

logger = logging.getLogger(__name__)

_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=settings.openai_api_key)
    return _client


async def transcribe(audio_path: Path) -> str:
    """Transcribe a WAV audio chunk to text using Whisper API.

    Returns the transcribed text, or empty string on failure.
    """
    client = _get_client()

    logger.info("Transcribing: %s", audio_path.name)

    with open(audio_path, "rb") as f:
        response = await client.audio.transcriptions.create(
            model=settings.whisper_model,
            file=f,
            language="ko",
            response_format="text",
        )

    text = response.strip() if isinstance(response, str) else str(response).strip()
    logger.info("Transcription (%d chars): %s", len(text), text[:80])
    return text
