from typing import Literal

from pydantic import BaseModel

from app.providers.llm import LLMProvider
from app.schemas.report import ReportDTO
from app.schemas.structured_review import StructuredReviewDTO
from app.services.structured_review_builder import (
    build_structured_review,
    build_structured_review_seed,
)

StructuredReviewProviderMode = Literal["rule", "llm"]
StructuredReviewState = Literal["success", "fallback", "failed"]


class StructuredReviewStatus(BaseModel):
    provider: str
    status: StructuredReviewState
    fallback_used: bool = False
    reason: str | None = None


def generate_structured_review(
    report: ReportDTO,
    llm_provider: LLMProvider,
    provider_mode: StructuredReviewProviderMode,
    fallback_enabled: bool,
) -> tuple[StructuredReviewDTO, StructuredReviewStatus]:
    if provider_mode == "rule":
        return build_structured_review(report), StructuredReviewStatus(
            provider="rule",
            status="success",
            fallback_used=False,
            reason=None,
        )
    if provider_mode != "llm":
        raise ValueError(f"Unsupported STRUCTURED_REVIEW_PROVIDER: {provider_mode}")

    try:
        review = llm_provider.generate_structured_review(build_structured_review_seed(report))
    except Exception as exc:
        reason = str(exc) or exc.__class__.__name__
        if not fallback_enabled:
            raise
        return build_structured_review(report), StructuredReviewStatus(
            provider="llm",
            status="fallback",
            fallback_used=True,
            reason=reason,
        )

    return review, StructuredReviewStatus(
        provider="llm",
        status="success",
        fallback_used=False,
        reason=None,
    )
