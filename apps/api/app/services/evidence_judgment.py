from __future__ import annotations

from app.schemas.evidence import EvidenceCategory, EvidenceConfidence, EvidenceItem
from app.schemas.structured_review import (
    EvidenceBackedConclusion,
    EvidenceBackedSignal,
    StructuredReviewDTO,
)


def apply_evidence_contract(
    review: StructuredReviewDTO,
    evidence: list[EvidenceItem],
) -> StructuredReviewDTO:
    high_evidence = [item for item in evidence if item.confidence == EvidenceConfidence.HIGH]
    review.evidence_conclusion = _build_evidence_conclusion(high_evidence)
    _attach_sector_evidence(review, high_evidence)
    _downgrade_unsupported_high_ratings(review, high_evidence)
    _enforce_capital_flow_gap(review, high_evidence)
    _attach_strategy_evidence(review, high_evidence)
    return review


def _build_evidence_conclusion(evidence: list[EvidenceItem]) -> EvidenceBackedConclusion:
    supported = [
        EvidenceBackedSignal(
            label=_signal_label(item),
            summary=item.claim,
            evidence_ids=[item.id],
            confidence=item.confidence.value,
            status="supported",
        )
        for item in evidence[:4]
    ]
    while len(supported) < 4:
        supported.append(
            EvidenceBackedSignal(
                label="待确认信号",
                summary="证据不足，暂不生成强结论。",
                evidence_ids=[],
                confidence="insufficient",
                status="insufficient",
            )
        )
    summary = (
        supported[0].summary
        if supported and supported[0].evidence_ids
        else "证据不足，核心结论保持保守。"
    )
    return EvidenceBackedConclusion(summary=summary, signals=supported)


def _attach_sector_evidence(review: StructuredReviewDTO, evidence: list[EvidenceItem]) -> None:
    for sector in review.sector_deep_dives:
        matched = _matching_sector_evidence(sector.sector, evidence)
        sector.evidence_ids = [item.id for item in matched]
        if matched:
            claims = [item.claim for item in matched[:2]]
            sector.capital_evidence.extend(
                claim for claim in claims if claim not in sector.capital_evidence
            )


def _downgrade_unsupported_high_ratings(
    review: StructuredReviewDTO, evidence: list[EvidenceItem]
) -> None:
    for sector in review.sector_deep_dives:
        if sector.rating == "high" and not _matching_sector_evidence(sector.sector, evidence):
            sector.rating = "medium"
            sector.conclusion = f"{sector.conclusion} 证据不足，评级降为观察。"
    for rank in review.sustainability_ranking:
        matched = _matching_sector_evidence(rank.sector, evidence)
        if rank.rating == "high" and not matched:
            rank.rating = "medium"
            rank.reason = f"{rank.reason} 证据不足，降为观察。"
        rank.evidence_ids = [item.id for item in matched]


def _matching_sector_evidence(sector: str, evidence: list[EvidenceItem]) -> list[EvidenceItem]:
    return [item for item in evidence if _evidence_matches_sector(sector, item)]


def _evidence_matches_sector(sector: str, item: EvidenceItem) -> bool:
    return sector in item.related_sectors or sector in item.claim or sector in item.title


def _enforce_capital_flow_gap(review: StructuredReviewDTO, evidence: list[EvidenceItem]) -> None:
    has_capital_flow = any(item.category == EvidenceCategory.CAPITAL_FLOW for item in evidence)
    if not has_capital_flow and "缺少已验证资金证据" not in review.capital_rotation.key_finding:
        review.capital_rotation.key_finding = (
            f"{review.capital_rotation.key_finding} 缺少已验证资金证据，资金轮动结论保持保守。"
        )
    if review.capital_rotation_v2 and not has_capital_flow:
        review.capital_rotation_v2.key_finding = (
            f"{review.capital_rotation_v2.key_finding} 缺少已验证资金证据，资金轮动结论保持保守。"
        )


def _attach_strategy_evidence(review: StructuredReviewDTO, evidence: list[EvidenceItem]) -> None:
    if review.next_session_strategy is None:
        return
    review.next_session_strategy.evidence_ids = [item.id for item in evidence[:4]]
    if not review.next_session_strategy.evidence_ids:
        review.next_session_strategy.focus = []
        review.next_session_strategy.observe = ["证据不足，等待资金与催化确认。"]


def _signal_label(item: EvidenceItem) -> str:
    labels = {
        EvidenceCategory.CAPITAL_FLOW: "资金信号",
        EvidenceCategory.CATALYST: "催化信号",
        EvidenceCategory.MARKET_SENTIMENT: "情绪信号",
        EvidenceCategory.LIMIT_UP: "强度信号",
        EvidenceCategory.RISK: "风险信号",
        EvidenceCategory.POLICY: "政策信号",
        EvidenceCategory.EARNINGS: "业绩信号",
    }
    return labels[item.category]
