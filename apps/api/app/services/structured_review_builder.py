from app.schemas.report import ReportDTO, SectorCandidate
from app.schemas.structured_review import (
    ActionDiscipline,
    MarketOverviewTable,
    PredictionReview,
    StructuredReviewDTO,
    StructuredSectorReview,
    SustainabilityRank,
    SustainabilityRating,
    TomorrowJudgement,
)


def build_structured_review(report: ReportDTO) -> StructuredReviewDTO:
    leader = report.sectors[0] if report.sectors else None
    runner_up = report.sectors[1] if len(report.sectors) > 1 else None
    leader_name = leader.name if leader else "暂无主线"
    runner_up_name = runner_up.name if runner_up else "暂无轮动方向"

    return StructuredReviewDTO(
        topic=_build_topic(report, leader, runner_up),
        prediction_review=PredictionReview(
            previous_prediction="昨日预判暂未接入自动回放，本阶段保留为结构化手动输入位。",
            actual_result=_build_actual_result(report),
            correct_items=[f"{leader_name}方向保持相对强势"] if leader else [],
            missed_items=["自动对比前一日报告尚未启用"],
            revision=f"后续预判重点观察{leader_name}与{runner_up_name}之间的资金切换。",
            source="manual_placeholder",
        ),
        tomorrow_judgement=TomorrowJudgement(
            most_likely_to_continue=leader_name,
            most_likely_to_diverge=runner_up_name,
            rotation_candidates=[sector.name for sector in report.sectors[1:4]],
            defensive_candidates=["高股息", "低位防御"],
            core_view=f"明日重点不是追高扩散，而是观察科技内部{leader_name}分歧后的承接与{runner_up_name}轮动强度。",
        ),
        market_overview=_build_market_overview(report),
        sector_reviews=[_build_sector_review(sector) for sector in report.sectors],
        sustainability_ranking=[
            SustainabilityRank(
                rank=index + 1,
                sector=sector.name,
                rating=_rating_for_sector(sector),
                reason=_sustainability_reason(sector),
            )
            for index, sector in enumerate(report.sectors)
        ],
        action_discipline=ActionDiscipline(
            focus=[f"优先观察{leader_name}核心标的承接"] if leader else ["等待新主线确认"],
            avoid=["回避无新闻催化的跟风补涨", "回避缩量冲高后回落的弱转强失败"],
            final_view=f"最实战的动作是围绕{leader_name}去弱留强，同时警惕高位一致后的分歧。",
        ),
    )


def _build_topic(report: ReportDTO, leader: SectorCandidate | None, runner_up: SectorCandidate | None) -> str:
    tag_text = "".join(report.market_state_tags) or "结构行情"
    leader_name = leader.name if leader else "暂无主线"
    if runner_up is None:
        return f"{tag_text} · {leader_name}领涨"
    return f"{tag_text} · {leader_name}领涨 · {runner_up.name}轮动"


def _build_actual_result(report: ReportDTO) -> str:
    sector_text = "、".join(sector.name for sector in report.sectors[:2]) or "暂无强势板块"
    market_state = "、".join(report.market_state_tags) or "结构性"
    return f"{report.trade_date}市场呈现{market_state}特征，{sector_text}相对靠前。"


def _build_market_overview(report: ReportDTO) -> MarketOverviewTable:
    return MarketOverviewTable(
        index_rows=[
            {
                "name": index.name,
                "close": f"{index.close:.2f}",
                "change": f"{index.pct_change:+.2f}%",
            }
            for index in report.indices
        ],
        emotion_rows=[
            {"label": "上涨 / 下跌", "value": f"{report.breadth.up_count} / {report.breadth.down_count}"},
            {"label": "涨停 / 跌停", "value": f"{report.breadth.limit_up_count} / {report.breadth.limit_down_count}"},
            {"label": "成交额", "value": f"{report.turnover_cny:.2f} 亿"},
        ],
        structure_features=report.market_state_tags,
        capital_flow_summary="资金不是简单流入流出，而是在强势板块之间做结构切换。",
    )


def _build_sector_review(sector: SectorCandidate) -> StructuredSectorReview:
    rating = _rating_for_sector(sector)
    return StructuredSectorReview(
        sector=sector.name,
        headline=f"{sector.name}：{_headline_suffix(rating)}",
        stage=_stage_for_rating(rating),
        strengths=[
            f"涨跌幅{sector.pct_change:+.2f}%",
            f"综合评分{sector.score:.1f}",
            *(sector.news_summaries[:1] or [sector.reason]),
        ],
        weaknesses=["短线一致后可能出现分歧", "后排跟风股承接要求更高"],
        logic="短线强度、板块广度与消息催化共同决定当前排序。",
        sustainability=rating,
        next_day_view=f"观察{sector.name}方向分歧后的核心股承接，而不是简单追逐后排补涨。",
        watch_items=[f"{sector.name}核心股回踩承接", "板块内强弱切换是否温和"],
        avoid_items=["缩量冲高回落", "无催化的低位跟风"],
    )


def _rating_for_sector(sector: SectorCandidate) -> SustainabilityRating:
    if sector.score >= 70 and sector.news_summaries:
        return "high"
    if sector.score >= 45:
        return "medium"
    return "low"


def _headline_suffix(rating: SustainabilityRating) -> str:
    return {
        "high": "主线承接仍强",
        "medium": "轮动强度待确认",
        "low": "持续性偏弱",
    }[rating]


def _stage_for_rating(rating: SustainabilityRating) -> str:
    return {
        "high": "主升延续",
        "medium": "轮动观察",
        "low": "弱修复",
    }[rating]


def _sustainability_reason(sector: SectorCandidate) -> str:
    if sector.news_summaries:
        return f"评分{sector.score:.1f}，且具备消息催化。"
    return f"评分{sector.score:.1f}，消息确认度仍需观察。"
