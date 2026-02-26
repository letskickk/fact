"""Stage 2: Fact-check using GPT-5.2 + web search (Responses API)."""

from __future__ import annotations

import json
import logging

from openai import AsyncOpenAI

from app.config import settings
from app.checker.prompts import VERIFIER_SYSTEM, VERIFIER_USER, VERIFIER_USER_WITH_CONTEXT
from app.models.schemas import FactCheckResult, Verdict

logger = logging.getLogger(__name__)

_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=settings.openai_api_key)
    return _client


async def verify(
    statement_id: str,
    text: str,
    context: str | None = None,
) -> FactCheckResult:
    """Fact-check a statement using GPT-5.2 with web search.

    Uses Responses API + web_search tool so the model searches
    the web for real-time verification before making a verdict.
    """
    client = _get_client()
    if context:
        user_msg = VERIFIER_USER_WITH_CONTEXT.format(statement=text, context=context)
    else:
        user_msg = VERIFIER_USER.format(statement=text)

    try:
        # Responses API with web_search (no JSON mode — incompatible with web_search)
        response = await client.responses.create(
            model=settings.verifier_model,
            instructions=VERIFIER_SYSTEM,
            input=user_msg,
            tools=[{"type": "web_search", "search_context_size": "medium"}],
        )
        raw = response.output_text or "{}"

    except Exception as e:
        logger.warning("Responses API error, falling back to chat: %s", e)
        response = await client.chat.completions.create(
            model=settings.verifier_model,
            messages=[
                {"role": "system", "content": VERIFIER_SYSTEM},
                {"role": "user", "content": user_msg},
            ],
            response_format={"type": "json_object"},
        )
        raw = response.choices[0].message.content or "{}"

    # Extract JSON from response (may contain markdown fences)
    raw = raw.strip()
    if raw.startswith("```"):
        lines = raw.split("\n")
        lines = [l for l in lines if not l.startswith("```")]
        raw = "\n".join(lines)

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("Failed to parse verifier response: %s", raw[:200])
        return FactCheckResult(
            statement_id=statement_id,
            statement_text=text,
            verdict=Verdict.UNVERIFIABLE,
            confidence=0.0,
            explanation="응답 파싱 실패",
        )

    verdict_str = data.get("verdict", "unverifiable")
    try:
        verdict = Verdict(verdict_str)
    except ValueError:
        verdict = Verdict.UNVERIFIABLE

    confidence = data.get("confidence", 0.5)
    confidence = max(0.0, min(1.0, float(confidence)))

    result = FactCheckResult(
        statement_id=statement_id,
        statement_text=text,
        verdict=verdict,
        confidence=confidence,
        explanation=data.get("explanation", ""),
        source_type=data.get("source_type", "web_search"),
        sources=data.get("sources", []),
    )

    logger.info(
        "Verification [%s]: %s (%.0f%%) — %s",
        statement_id,
        result.verdict.value,
        result.confidence * 100,
        result.explanation[:80],
    )
    return result
