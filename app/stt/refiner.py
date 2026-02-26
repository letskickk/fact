"""LLM-based transcript refinement.

Whisper 결과의 오타, 동음이의어, 고유명사, 문장 구분 등을 보정.
"""

from __future__ import annotations

import logging

from openai import AsyncOpenAI

from app.config import settings

logger = logging.getLogger(__name__)

_client: AsyncOpenAI | None = None

REFINE_SYSTEM = """\
당신은 한국어 음성인식 결과를 보정하는 전문가입니다.

입력: Whisper STT가 출력한 원본 텍스트 (실시간 유튜브 방송 음성)

작업:
1. 오탈자/동음이의어 보정 (예: "부정선거" ↔ "부정 선거", "대통령" 등 고유명사 정확히)
2. 문맥상 잘못 인식된 단어 교정
3. 불필요한 반복/더듬기 제거 ("어어 그 그니까" → 적절히 정리)
4. 문장 부호 추가 (마침표, 쉼표 등)
5. 의미가 불분명한 부분은 원문 유지

규칙:
- 원래 의미를 절대 바꾸지 마세요
- 없는 내용을 추가하지 마세요
- 핵심 발언과 주장은 반드시 보존하세요
- 보정된 텍스트만 출력하세요 (설명 없이)
"""


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=settings.openai_api_key)
    return _client


async def refine(raw_text: str) -> str:
    """Refine raw Whisper transcription using LLM.

    Returns refined text, or original text on failure.
    """
    if not raw_text or len(raw_text) < 5:
        return raw_text

    client = _get_client()

    try:
        response = await client.responses.create(
            model=settings.classifier_model,  # gpt-5-nano (fast + cheap)
            instructions=REFINE_SYSTEM,
            input=raw_text,
        )

        refined = response.output_text.strip()

        if refined and len(refined) >= len(raw_text) * 0.3:
            logger.info("Refined (%d→%d chars): %s", len(raw_text), len(refined), refined[:80])
            return refined
        else:
            logger.warning("Refinement too short, using original")
            return raw_text

    except Exception as e:
        logger.warning("Refinement failed, using original: %s", e)
        return raw_text
