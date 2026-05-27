import re

from app.schemas.report import (
    IndexSnapshot,
    MarketBreadth,
    NextDayPrediction,
    ReportDTO,
    ReportKind,
    ReportNarrative,
    SectorCandidate,
)
from app.schemas.structured_review import (
    ActionDiscipline,
    AfterHoursNewsSummary,
    CapitalRotationPath,
    IndexMidTermOutlook,
    MarketOverviewTable,
    NextDayOpportunityPlan,
    PracticalConclusion,
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
    top_prediction = _top_numeric_prediction(report)
    leader_name = top_prediction.sector if top_prediction is not None else leader.name if leader else "暂无主线"
    runner_up_name = runner_up.name if runner_up else "暂无轮动方向"
    previous_theme_names = [item.theme for item in report.previous_strong_themes if item.judgement != "延续确认"]
    diverge_name = "、".join(previous_theme_names[:3]) if previous_theme_names else runner_up_name

    return StructuredReviewDTO(
        topic=_build_topic(report, leader, runner_up),
        prediction_review=PredictionReview(
            previous_prediction=_previous_prediction_text(report),
            actual_result=_build_actual_result(report),
            correct_items=[f"{leader_name}方向保持相对强势"] if leader else [],
            missed_items=_missed_items(report),
            bias_reasons=[
                _history_bias_reason(report),
                f"{runner_up_name}的轮动强度需要结合次日竞价与量能继续确认。",
            ],
            revision=f"后续预判重点观察{leader_name}与{runner_up_name}之间的资金切换。",
            source="previous_report" if report.previous_strong_themes else "manual_placeholder",
        ),
        tomorrow_judgement=TomorrowJudgement(
            most_likely_to_continue=leader_name,
            most_likely_to_diverge=diverge_name,
            rotation_candidates=[sector.name for sector in report.sectors[1:4]],
            defensive_candidates=["高股息", "低位防御"],
            core_view=f"明日重点不是追高扩散，而是观察{leader_name}分歧后的承接与{runner_up_name}轮动强度。",
            operating_focus=[
                f"先看{leader_name}是否温和分歧后继续承接。",
                f"再看{runner_up_name}能否从轮动转为持续。",
                "若指数放量下杀，优先降低节奏预期。",
            ],
        ),
        market_overview=_build_market_overview(report),
        after_hours_news=_build_after_hours_news(report),
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
        capital_rotation=_build_capital_rotation(report, leader, runner_up),
        historical_theme_reviews=report.previous_strong_themes,
        next_day_opportunity=_build_next_day_opportunity(report, leader),
        practical_conclusion=_build_practical_conclusion(leader_name, runner_up_name),
        index_mid_term_outlook=_build_index_mid_term_outlook(report),
        action_discipline=ActionDiscipline(
            focus=[f"优先观察{leader_name}核心标的承接"] if leader else ["等待新主线确认"],
            avoid=["回避无新闻催化的跟风补涨", "回避缩量冲高后回落的弱转强失败"],
            final_view=f"最实战的动作是围绕{leader_name}去弱留强，同时警惕高位一致后的分歧。",
        ),
    )


def _previous_prediction_text(report: ReportDTO) -> str:
    if not report.previous_strong_themes:
        return "昨日预判暂未接入自动回放，本阶段保留为结构化手动输入位。"
    themes = "、".join(item.theme for item in report.previous_strong_themes[:4])
    return f"前一报告重点跟踪：{themes}。今日需要验证这些方向是延续、分化、退潮还是修复。"


def _missed_items(report: ReportDTO) -> list[str]:
    if not report.previous_strong_themes:
        return ["自动对比前一日报告尚未启用"]
    items = []
    for theme in report.previous_strong_themes:
        if theme.judgement == "延续确认":
            continue
        items.append(f"{theme.theme}{theme.current_status}，判断为{theme.judgement}。")
    return items or ["前期强势主线仍在今日前排中延续。"]


def _history_bias_reason(report: ReportDTO) -> str:
    if not report.previous_strong_themes:
        return "当前版本尚未接入前一交易日报告回放，因此偏差归因以当日结构变化为主。"
    return "已接入前一报告主线回放，偏差归因优先看前期强势方向是否继续进入今日前排。"


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
        structure_notes=[
            f"{report.market_state_tags[0]}是当前盘面的第一标签。" if report.market_state_tags else "结构标签暂不明确。",
            f"强势方向集中在{report.sectors[0].name}，扩散质量仍需观察。" if report.sectors else "强势方向暂不明确。",
            "涨跌家数与涨跌停数量共同决定短线情绪温度。",
        ],
        capital_flow_summary="资金不是简单流入流出，而是在强势板块之间做结构切换。",
    )


def _build_after_hours_news(report: ReportDTO) -> AfterHoursNewsSummary:
    domestic = [item.title for item in report.news[:4] if item.title]
    if not domestic:
        domestic = [f"{sector.name}方向消息确认度仍需结合次日竞价观察" for sector in report.sectors[:2]]
    us_mapping = (
        [f"海外映射重点观察{report.sectors[0].name}产业链反馈"]
        if report.sectors
        else ["海外映射暂未形成明确方向"]
    )
    return AfterHoursNewsSummary(
        us_market_mapping=us_mapping,
        us_market_conclusion=(
            f"海外线索主要作为{report.sectors[0].name}产业链映射观察。"
            if report.sectors
            else "海外映射暂未形成明确方向。"
        ),
        domestic_catalysts=domestic[:4],
        risk_notes=["盘后消息只作为次日观察线索，不作为单独决策依据。"],
    )


def _build_capital_rotation(
    report: ReportDTO,
    leader: SectorCandidate | None,
    runner_up: SectorCandidate | None,
) -> CapitalRotationPath:
    sector_names = [sector.name for sector in report.sectors[:4]]
    actual_path = [
        f"{name}承接" if index == 0 else f"{name}轮动" for index, name in enumerate(sector_names)
    ]
    if not actual_path:
        actual_path = ["等待主线确认"]
    leader_name = leader.name if leader else "暂无主线"
    runner_up_name = runner_up.name if runner_up else "暂无轮动方向"
    return CapitalRotationPath(
        actual_path=actual_path,
        path_summary=" → ".join(actual_path),
        key_finding=f"资金仍围绕{leader_name}展开，但{runner_up_name}的轮动强度决定次日扩散质量。",
        next_path_watch=[
            f"观察{leader_name}分歧后的回流强度",
            f"观察{runner_up_name}是否从轮动转为持续",
            "观察防御方向是否只是一日避险",
        ],
    )


def _build_next_day_opportunity(
    report: ReportDTO, leader: SectorCandidate | None
) -> NextDayOpportunityPlan:
    prediction_focus = _prediction_focus_candidates(report)
    if prediction_focus:
        focus = prediction_focus
    else:
        leader_name = leader.name if leader else "主线"
        focus = _next_day_focus_candidates(report, leader_name)
    return NextDayOpportunityPlan(
        focus_candidates=focus,
        position_discipline=[
            "只观察确认后的承接，不追一致加速；默认空仓/轻仓观察。",
            "只有前排股分歧后重新转强，才考虑试探底仓。",
            "单一方向底仓不超过2成；主线确认扩散后，总仓位上限控制在3成以内。",
            "弱分支只看修复，不做主线预设；缩量冲高不加仓。",
        ],
        trigger_conditions=["指数不出现明显放量下杀", "主线前排分歧温和", "成交额维持活跃区间"],
        avoid_conditions=["缩量冲高回落", "无催化后排补涨", "高位一致加速后的被动追高"],
    )


def _top_numeric_prediction(report: ReportDTO) -> NextDayPrediction | None:
    numeric = [item for item in report.next_day_predictions if item.continuation_probability is not None]
    if not numeric:
        return None
    return sorted(
        numeric,
        key=lambda item: (item.continuation_probability or 0, -item.rank),
        reverse=True,
    )[0]


def _prediction_focus_candidates(report: ReportDTO) -> list[str]:
    prediction = _top_numeric_prediction(report)
    if prediction is None:
        return []
    focus = [_prediction_stock_candidate_text(stock) for stock in prediction.front_row_stocks[:3] if stock.name]
    if focus:
        return focus
    return prediction.trigger_conditions[:2]


def _prediction_stock_candidate_text(stock: object) -> str:
    name = getattr(stock, "name", "")
    code = getattr(stock, "code", "")
    observation = getattr(stock, "observation", "")
    identity = f"{name} {code}".strip()
    return f"{identity}：{observation}" if observation else identity


def _next_day_focus_candidates(report: ReportDTO, leader_name: str) -> list[str]:
    focus: list[str] = []
    for sector in report.sectors[:3]:
        stock_text = _stock_candidate_text(sector.top_stocks[:3])
        if stock_text:
            focus.append(f"{sector.name}：观察{stock_text}分歧后的承接确认")
        elif sector.name == leader_name:
            focus.append(f"{leader_name}核心股承接确认")
        else:
            focus.append(f"{sector.name}前排分歧转强")
    return focus or [f"{leader_name}核心股承接确认"]


def _stock_candidate_text(stocks: list[object]) -> str:
    parts = []
    for stock in stocks:
        name = getattr(stock, "name", "")
        code = getattr(stock, "code", "")
        if not name:
            continue
        parts.append(f"{name} {code}".strip())
    return "、".join(parts)


def _build_practical_conclusion(leader_name: str, runner_up_name: str) -> PracticalConclusion:
    return PracticalConclusion(
        headline=f"明日最实战的观察，是围绕{leader_name}去弱留强，同时确认{runner_up_name}是否具备持续性。",
        bullet_points=[
            f"先看{leader_name}核心股承接，而不是后排补涨。",
            f"再看{runner_up_name}能否从轮动变成持续。",
            "如果指数放量下杀，优先降低节奏预期。",
        ],
    )


def _build_index_mid_term_outlook(report: ReportDTO) -> IndexMidTermOutlook:
    index_name = report.indices[0].name if report.indices else "上证指数"
    index_change = report.indices[0].pct_change if report.indices else 0
    position = "偏强修复" if index_change >= 0 else "震荡承压"
    return IndexMidTermOutlook(
        year_review=[
            f"{index_name}当前更像结构行情载体，指数方向需要结合成交额和主线扩散判断。",
            "年度级别判断暂不预设单边趋势，优先跟踪量能与赚钱效应。",
        ],
        current_position=(
            f"{report.trade_date}收盘后，指数处于{position}状态，"
            "短线重点看强势板块是否带动赚钱效应扩散。"
        ),
        scenario_table=[
            {"scenario": "强势延续", "condition": "指数放量上行且主线扩散", "response": "观察核心方向承接与轮动扩散"},
            {"scenario": "震荡分化", "condition": "指数量能持平且板块轮动", "response": "控制节奏，优先去弱留强"},
            {"scenario": "转弱防守", "condition": "指数放量下杀且高位退潮", "response": "降低预期，回避后排补涨"},
        ],
    )


def _build_sector_review(sector: SectorCandidate) -> StructuredSectorReview:
    rating = _rating_for_sector(sector)
    news_evidence = _compact_news_evidence(sector.news_summaries)
    review_evidence = _compact_news_evidence(sector.review_notes, max_length=96)
    front_row_text = _front_row_stock_text(sector)
    source_text = "、".join(sector.review_sources) if sector.review_sources else "复盘源暂未确认"
    return StructuredSectorReview(
        sector=sector.name,
        headline=f"{sector.name}：{_headline_suffix(rating)}",
        stage=_stage_for_rating(rating),
        strengths=[
            f"涨跌幅{sector.pct_change:+.2f}%",
            f"综合评分{sector.score:.1f}",
            front_row_text or "前排个股仍待复盘源确认",
            review_evidence or news_evidence or sector.reason,
        ],
        weaknesses=["后排跟风股承接要求更高", "若前排放量开板，板块容易分化"],
        logic=f"{sector.name}的判断优先看前排股强度，其次看同花顺/东方财富复盘源是否共同确认。",
        logic_points=[
            f"价格强度：板块涨跌幅{sector.pct_change:+.2f}%。",
            f"评分结构：综合评分{sector.score:.1f}，排名第{sector.rank}。",
            f"复盘源确认：{source_text}。",
            f"前排个股：{front_row_text or '暂未解析到明确前排股'}。",
        ],
        sustainability_analysis=_sustainability_analysis(sector, rating),
        sustainability=rating,
        next_day_view=f"观察{sector.name}前排股分歧后的承接，优先看{front_row_text or '核心股'}，不追后排补涨。",
        watch_items=[f"{sector.name}前排股竞价和开盘承接", "板块内强弱切换是否温和"],
        avoid_items=["缩量冲高回落", "无复盘源确认的低位跟风"],
    )


def _sustainability_analysis(sector: SectorCandidate, rating: SustainabilityRating) -> str:
    if rating == "high":
        return f"{sector.name}同时具备较高评分与消息确认度，次日更适合观察分歧承接。"
    if rating == "medium":
        return f"{sector.name}处在轮动观察区，持续性取决于前排是否继续扩散。"
    return f"{sector.name}当前持续性偏弱，更适合作为观察对象而非追高方向。"


def _compact_news_evidence(news_summaries: list[str], max_length: int = 72) -> str | None:
    for summary in news_summaries:
        normalized = re.sub(r"\s+", " ", summary).strip()
        if not normalized:
            continue
        for marker in (" 基本资料", " 公司全称", " 联系电话", " 传真", " 工商登记"):
            marker_index = normalized.find(marker)
            if marker_index > 0:
                normalized = normalized[:marker_index].strip()
        if len(normalized) > max_length:
            normalized = f"{normalized[: max_length - 1].rstrip()}…"
        return normalized
    return None


def _rating_for_sector(sector: SectorCandidate) -> SustainabilityRating:
    if sector.score >= 70 and (sector.news_summaries or sector.review_sources):
        return "high"
    if sector.score >= 45:
        return "medium"
    return "low"


def _front_row_stock_text(sector: SectorCandidate) -> str:
    stocks = [stock for stock in sector.top_stocks if stock.name]
    return "、".join(f"{stock.name}{stock.pct_change:+.2f}%" for stock in stocks[:4])


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


def build_structured_review_seed(report: ReportDTO) -> dict[str, object]:
    return {
        "trade_date": report.trade_date,
        "indices": [index.model_dump(mode="json") for index in report.indices],
        "breadth": report.breadth.model_dump(mode="json"),
        "turnover_cny": report.turnover_cny,
        "market_state_tags": report.market_state_tags,
        "sectors": [
            {
                "name": sector.name,
                "rank": sector.rank,
                "score": sector.score,
                "pct_change": sector.pct_change,
                "factor_scores": sector.factor_scores,
                "news_summaries": sector.news_summaries,
            }
            for sector in report.sectors
        ],
        "news": [item.model_dump(mode="json") for item in report.news],
        "narrative": report.narrative.model_dump(mode="json"),
    }


def build_structured_review_from_seed(seed: dict[str, object]) -> StructuredReviewDTO:
    report = ReportDTO(
        trade_date=str(seed.get("trade_date") or "unknown"),
        kind=ReportKind.CLOSE,
        title=f"{seed.get('trade_date') or 'unknown'} A股复盘",
        indices=[IndexSnapshot.model_validate(item) for item in seed.get("indices", [])],
        breadth=MarketBreadth.model_validate(seed.get("breadth", {})),
        turnover_cny=float(seed.get("turnover_cny") or 0),
        market_state_tags=[str(item) for item in seed.get("market_state_tags", [])],
        sectors=[],
        narrative=ReportNarrative(
            conclusion="",
            overview="",
            sector_commentary=[],
            watchlist=[],
            tomorrow="",
            risks=[],
        ),
        news=[],
    )
    return build_structured_review(report)
