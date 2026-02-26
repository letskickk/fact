"""Stage 1: Classify whether a statement needs fact-checking (GPT-5 Nano)."""

from __future__ import annotations

import json
import logging

from openai import AsyncOpenAI

from app.config import settings
from app.checker.prompts import CLASSIFIER_SYSTEM, CLASSIFIER_USER
from app.models.schemas import ClassificationResult, ClaimType

logger = logging.getLogger(__name__)

_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=settings.openai_api_key)
    return _client


async def classify(statement_id: str, text: str) -> ClassificationResult:
    """Classify whether a statement needs fact-checking.

    Uses GPT-5 Nano for fast, cheap classification.
    """
    client = _get_client()

    response = await client.chat.completions.create(
        model=settings.classifier_model,
        messages=[
            {"role": "system", "content": CLASSIFIER_SYSTEM},
            {"role": "user", "content": CLASSIFIER_USER.format(statement=text)},
        ],
        response_format={"type": "json_object"},
    )

    raw = response.choices[0].message.content or "{}"
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("Failed to parse classifier response: %s", raw)
        return ClassificationResult(
            statement_id=statement_id,
            needs_check=False,
            reason="parse error",
        )

    claim_type = data.get("claim_type", "other")
    try:
        claim_type = ClaimType(claim_type)
    except ValueError:
        claim_type = ClaimType.OTHER

    result = ClassificationResult(
        statement_id=statement_id,
        needs_check=data.get("needs_check", False),
        claim_type=claim_type,
        reason=data.get("reason", ""),
    )

    logger.info(
        "Classification [%s]: needs_check=%s, type=%s",
        statement_id,
        result.needs_check,
        result.claim_type.value,
    )
    return result
