from app.schemas.evidence import (
    EvidenceCategory,
    EvidenceConfidence,
    EvidenceItem,
    EvidenceStatus,
)
from app.schemas.structured_review import (
    ActionDiscipline,
    AfterHoursNewsSummary,
    CapitalRotationPath,
    IndexMidTermOutlook,
    MarketOverviewTable,
    NextDayOpportunityPlan,
    PredictionReview,
    PracticalConclusion,
    SectorDeepDive,
    StructuredReviewDTO,
    SustainabilityRank,
    TomorrowJudgement,
)
from app.services.evidence_judgment import apply_evidence_contract


def _evidence(**overrides) -> EvidenceItem:
    base = {
        "id": "ev_20260601_001",
        "trade_date": "2026-06-01",
        "source": "证券时报",
        "title": "煤炭行业净流入",
        "url": "https://example.com/stcn/coal",
        "published_at": "2026-06-01T15:30:00+08:00",
        "category": EvidenceCategory.CAPITAL_FLOW,
        "claim": "煤炭行业今日净流入资金26.55亿元。",
        "numbers": {"industry": "煤炭", "net_inflow_yi": 26.55},
        "related_sectors": ["煤炭"],
        "confidence": EvidenceConfidence.HIGH,
        "status": EvidenceStatus.VERIFIED,
    }
    base.update(overrides)
    return EvidenceItem(**base)


def _review() -> StructuredReviewDTO:
    return StructuredReviewDTO(
        topic="结构复盘",
        prediction_review=PredictionReview(
            previous_prediction="无",
            actual_result="无",
            revision="继续观察",
        ),
        tomorrow_judgement=TomorrowJudgement(
            most_likely_to_continue="煤炭",
            most_likely_to_diverge="电子",
            core_view="围绕证据强的方向处理。",
        ),
        market_overview=MarketOverviewTable(capital_flow_summary="市场震荡。"),
        after_hours_news=AfterHoursNewsSummary(),
        sector_deep_dives=[
            SectorDeepDive(
                sector="煤炭",
                stage="leader",
                rating="high",
                catalysts=[],
                core_stocks=[],
                capital_evidence=[],
                conclusion="煤炭资金占优。",
            ),
            SectorDeepDive(
                sector="机器人",
                stage="leader",
                rating="high",
                catalysts=[],
                core_stocks=[],
                capital_evidence=[],
                conclusion="机器人继续重点关注。",
            ),
        ],
        sustainability_ranking=[
            SustainabilityRank(rank=1, sector="煤炭", rating="high", reason="资金强。"),
            SustainabilityRank(rank=2, sector="机器人", rating="high", reason="题材强。"),
        ],
        capital_rotation=CapitalRotationPath(key_finding="资金集中。"),
        next_day_opportunity=NextDayOpportunityPlan(),
        practical_conclusion=PracticalConclusion(headline="关注证据最强方向。"),
        index_mid_term_outlook=IndexMidTermOutlook(current_position="震荡。"),
        action_discipline=ActionDiscipline(final_view="证据优先。"),
    )


def test_apply_evidence_contract_creates_four_core_signals() -> None:
    review = apply_evidence_contract(
        _review(),
        [
            _evidence(id="ev_20260601_001", claim="煤炭行业今日净流入资金26.55亿元。"),
            _evidence(
                id="ev_20260601_002",
                category=EvidenceCategory.CATALYST,
                claim="英伟达N1X AI PC芯片催化AI PC方向。",
                related_sectors=["AI PC"],
                numbers={},
            ),
        ],
    )

    assert review.evidence_conclusion is not None
    assert len(review.evidence_conclusion.signals) == 4
    assert review.evidence_conclusion.signals[0].evidence_ids == ["ev_20260601_001"]


def test_sector_without_high_evidence_is_downgraded_from_high() -> None:
    review = apply_evidence_contract(_review(), [_evidence()])

    robot = next(item for item in review.sector_deep_dives if item.sector == "机器人")
    assert robot.rating == "medium"
    assert "证据不足" in robot.conclusion


def test_sector_claim_or_title_match_supports_high_rating_without_related_sector() -> None:
    review = apply_evidence_contract(
        _review(),
        [
            _evidence(
                id="ev_20260601_010",
                category=EvidenceCategory.CATALYST,
                title="机器人板块催化持续",
                claim="机器人产业链出现新增催化。",
                related_sectors=[],
                numbers={},
            )
        ],
    )

    robot = next(item for item in review.sector_deep_dives if item.sector == "机器人")
    robot_rank = next(item for item in review.sustainability_ranking if item.sector == "机器人")
    assert robot.rating == "high"
    assert robot.evidence_ids == ["ev_20260601_010"]
    assert robot_rank.rating == "high"
    assert robot_rank.evidence_ids == ["ev_20260601_010"]


def test_missing_capital_flow_evidence_adds_gap_message() -> None:
    review = apply_evidence_contract(
        _review(),
        [
            _evidence(
                category=EvidenceCategory.CATALYST,
                claim="宇树科技科创板IPO过会。",
                related_sectors=["机器人"],
                numbers={},
            )
        ],
    )

    assert "缺少已验证资金证据" in review.capital_rotation.key_finding
