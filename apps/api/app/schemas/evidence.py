from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class EvidenceCategory(StrEnum):
    CAPITAL_FLOW = "capital_flow"
    CATALYST = "catalyst"
    MARKET_SENTIMENT = "market_sentiment"
    LIMIT_UP = "limit_up"
    RISK = "risk"
    POLICY = "policy"
    EARNINGS = "earnings"


class EvidenceConfidence(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class EvidenceStatus(StrEnum):
    CANDIDATE = "candidate"
    DRAFT = "draft"
    VERIFIED = "verified"


class EvidenceInput(BaseModel):
    id: str | None = None
    trade_date: str
    source: str
    title: str
    url: str
    published_at: str
    category: EvidenceCategory
    claim: str
    numbers: dict[str, Any] = Field(default_factory=dict)
    related_sectors: list[str] = Field(default_factory=list)
    confidence: EvidenceConfidence = EvidenceConfidence.MEDIUM
    status: EvidenceStatus = EvidenceStatus.DRAFT
    manual_confirmed: bool = False


class EvidenceItem(EvidenceInput):
    id: str


class EvidencePreviewItem(BaseModel):
    raw: dict[str, Any] | str
    item: EvidenceInput | None = None
    errors: list[str] = Field(default_factory=list)


class EvidenceParsePreview(BaseModel):
    items: list[EvidencePreviewItem] = Field(default_factory=list)
    valid_count: int = 0
    invalid_count: int = 0


class EvidenceParsePreviewRequest(BaseModel):
    content: str


class EvidenceSaveRequest(BaseModel):
    items: list[EvidenceInput]


class EvidenceListResponse(BaseModel):
    items: list[EvidenceItem]


class EvidenceCandidateRequest(BaseModel):
    trade_date: str
    query: str = ""
    task: str = "custom"


class EvidenceCandidateResponse(BaseModel):
    items: list[EvidencePreviewItem]
    provider_status: dict[str, object]
