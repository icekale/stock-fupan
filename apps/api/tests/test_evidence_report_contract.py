from app.schemas.evidence import (
    EvidenceCategory,
    EvidenceConfidence,
    EvidenceItem,
    EvidenceStatus,
)
from app.rules.validation import validate_evidence_contract
from app.schemas.report import (
    IndexSnapshot,
    MarketBreadth,
    ReportDTO,
    ReportKind,
    ReportNarrative,
    SectorCandidate,
)
from app.schemas.structured_review import (
    ActionDiscipline,
    AfterHoursNewsSummary,
    CapitalRotationPath,
    CapitalRotationReviewV2,
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


def test_missing_capital_flow_gap_message_is_idempotent_for_v1_and_v2() -> None:
    review = _review()
    review.capital_rotation_v2 = CapitalRotationReviewV2(
        rotation_type="观察",
        key_finding="资金集中。",
    )
    evidence = [
        _evidence(
            category=EvidenceCategory.CATALYST,
            claim="宇树科技科创板IPO过会。",
            related_sectors=["机器人"],
            numbers={},
        )
    ]

    apply_evidence_contract(review, evidence)
    apply_evidence_contract(review, evidence)

    assert review.capital_rotation.key_finding.count("缺少已验证资金证据") == 1
    assert review.capital_rotation_v2 is not None
    assert review.capital_rotation_v2.key_finding.count("缺少已验证资金证据") == 1


def test_validate_evidence_contract_flags_supported_outputs_without_evidence_ids() -> None:
    review = apply_evidence_contract(_review(), [_evidence()])
    assert review.evidence_conclusion is not None
    review.evidence_conclusion.signals[0].evidence_ids = []
    coal = next(item for item in review.sector_deep_dives if item.sector == "煤炭")
    coal.evidence_ids = []

    report = ReportDTO(
        trade_date="2026-06-01",
        kind=ReportKind.CLOSE,
        title="2026-06-01-收盘复盘",
        indices=[IndexSnapshot(name="上证指数", code="000001", close=3100.0, pct_change=0.1)],
        breadth=MarketBreadth(up_count=1, down_count=1, limit_up_count=1, limit_down_count=0),
        turnover_cny=100_000_000_000,
        market_state_tags=["震荡"],
        sectors=[
            SectorCandidate(
                name="煤炭",
                score=90,
                rank=1,
                pct_change=2.0,
                reason="资金强。",
            )
        ],
        narrative=ReportNarrative(
            conclusion="煤炭占优。",
            overview="市场震荡。",
            sector_commentary=[],
            watchlist=[],
            tomorrow="继续观察。",
            risks=[],
        ),
        structured_review=review,
    )

    assert validate_evidence_contract(report) == [
        "supported signal lacks evidence ids: 资金信号",
        "high sector rating lacks evidence ids: 煤炭",
    ]
