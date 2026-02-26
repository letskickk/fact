from __future__ import annotations

import uuid
from enum import Enum

from pydantic import BaseModel, Field


class Verdict(str, Enum):
    FACT = "fact"
    PARTIAL = "partial"
    FALSE = "false"
    UNVERIFIABLE = "unverifiable"


class ClaimType(str, Enum):
    STATISTIC = "statistic"
    HISTORICAL = "historical"
    LEGAL = "legal"
    QUOTE = "quote"
    OTHER = "other"


class Statement(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8])
    text: str
    timestamp: float = 0.0
    speaker: str | None = None


class ClassificationResult(BaseModel):
    statement_id: str
    needs_check: bool
    claim_type: ClaimType = ClaimType.OTHER
    reason: str = ""


class FactCheckResult(BaseModel):
    statement_id: str
    statement_text: str = ""
    verdict: Verdict
    confidence: float = Field(ge=0.0, le=1.0)
    explanation: str
    source_type: str = ""  # "reference", "web_search", "llm", or combo
    sources: list[str] = Field(default_factory=list)


# WebSocket event payloads

class WSEvent(BaseModel):
    type: str
    data: dict


class SessionStartRequest(BaseModel):
    youtube_url: str


class SessionStatus(BaseModel):
    session_id: str
    status: str  # "running" | "stopped" | "error"
    youtube_url: str = ""
