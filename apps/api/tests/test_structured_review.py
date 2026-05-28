import pytest

from app.providers.llm import FakeLLMProvider, LLMFallbackError
from app.providers.market import FakeMarketDataProvider
from app.providers.news import FakeNewsProvider
from app.rules.scoring import score_sectors
from app.schemas.report import (
    NextDayPrediction,
    PredictionConfidence,
    PredictionStockFocus,
    ReportDTO,
    ReportKind,
    SectorCandidate,
    StockCandidate,
)
from app.schemas.structured_review import (
    ActionDiscipline,
    AfterHoursNewsSummary,
    CapitalRotationPath,
    HistoricalThemeReview,
    IndexMidTermOutlook,
    MarketOverviewTable,
    NextDayOpportunityPlan,
    PracticalConclusion,
    PredictionReview,
    StructuredReviewDTO,
    StructuredSectorReview,
    SustainabilityRank,
    TomorrowJudgement,
)
from app.services.structured_review_builder import build_structured_review
from app.services.structured_review_generator import generate_structured_review


def test_structured_review_serializes_core_modules() -> None:
    review = StructuredReviewDTO(
        topic="科技内部淘汰赛 · 主线换挡日",
        prediction_review=PredictionReview(
            previous_prediction="昨日预判机器人方向分歧后仍有承接。",
            actual_result="机器人方向继续领涨，PCB轮动增强。",
            correct_items=["机器人方向延续强势"],
            missed_items=["PCB强度高于预期"],
            bias_reasons=["昨日对PCB轮动估计偏保守"],
            revision="明日观察机器人与PCB之间的资金切换。",
            source="manual_placeholder",
        ),
        tomorrow_judgement=TomorrowJudgement(
            most_likely_to_continue="机器人",
            most_likely_to_diverge="PCB",
            rotation_candidates=["PCB"],
            defensive_candidates=["高股息"],
            core_view="主线仍在科技内部轮动，去弱留强。",
            operating_focus=["先看机器人承接", "再看PCB扩散"],
        ),
        market_overview=MarketOverviewTable(
            index_rows=[{"name": "上证指数", "close": "3100.50", "change": "+1.20%"}],
            emotion_rows=[{"label": "涨停 / 跌停", "value": "86 / 8"}],
            structure_features=["放量", "分化"],
            structure_notes=["科技内部强弱分化"],
            capital_flow_summary="资金集中在科技方向内部轮动。",
        ),
        after_hours_news=AfterHoursNewsSummary(
            us_market_mapping=["英伟达链条映射仍需观察"],
            us_market_conclusion="美股映射只作为观察线索",
            domestic_catalysts=["机器人产业催化延续"],
            risk_notes=["盘后消息只作为次日观察线索"],
        ),
        sector_reviews=[
            StructuredSectorReview(
                sector="机器人",
                headline="机器人：主线承接仍强",
                stage="主升延续",
                strengths=["涨幅居前", "新闻催化明确"],
                weaknesses=["高位分歧可能加大"],
                logic="产业消息与短线强度共振。",
                logic_points=["产业消息催化", "短线强度居前"],
                sustainability_analysis="主线承接仍强，但高位分歧需要观察。",
                sustainability="high",
                next_day_view="观察分歧后的核心股承接。",
                watch_items=["核心股回踩不破均线"],
                avoid_items=["缩量冲高回落"],
            )
        ],
        sustainability_ranking=[
            SustainabilityRank(rank=1, sector="机器人", rating="high", reason="强度和催化同时领先")
        ],
        capital_rotation=CapitalRotationPath(
            actual_path=["机器人承接", "PCB轮动", "防御补位"],
            path_summary="机器人承接 → PCB轮动 → 防御补位",
            key_finding="科技内部仍是资金轮动主场。",
            next_path_watch=["观察机器人分歧后是否回流", "观察PCB是否继续扩散"],
        ),
        historical_theme_reviews=[
            HistoricalThemeReview(
                theme="先进封装",
                previous_status="昨日持续性高",
                current_status="今日未进入前排",
                judgement="降级观察",
                evidence=["昨日核心股：长电科技+10.00%"],
                current_stock_checks=["长电科技 600584.SH 今日-3.20%"],
                watch_items=["观察长电科技能否重新转强"],
            )
        ],
        next_day_opportunity=NextDayOpportunityPlan(
            focus_candidates=["机器人核心股承接", "PCB前排分歧转强"],
            position_discipline=["只观察确认后的承接，不追一致加速"],
            trigger_conditions=["指数不明显放量下杀", "主线前排分歧温和"],
            avoid_conditions=["缩量冲高回落", "无催化后排补涨"],
        ),
        practical_conclusion=PracticalConclusion(
            headline="明日重点是科技内部去弱留强。",
            bullet_points=["先看机器人承接", "再看PCB轮动强度", "弱分支不追高"],
        ),
        index_mid_term_outlook=IndexMidTermOutlook(
            year_review=["指数处于结构性修复阶段"],
            current_position="当前位置更适合观察量能和主线扩散，而不是预设单边趋势。",
            scenario_table=[
                {"scenario": "强势", "condition": "放量上行", "response": "观察主线扩散"},
                {"scenario": "震荡", "condition": "量能持平", "response": "控制节奏"},
            ],
        ),
        action_discipline=ActionDiscipline(
            focus=["保留机器人核心方向观察"],
            avoid=["回避无催化的跟风补涨"],
            final_view="明日重点是科技内部去弱留强。",
        ),
    )

    payload = review.model_dump(mode="json")

    assert payload["topic"] == "科技内部淘汰赛 · 主线换挡日"
    assert payload["prediction_review"]["source"] == "manual_placeholder"
    assert payload["sector_reviews"][0]["sustainability"] == "high"
    assert payload["action_discipline"]["avoid"] == ["回避无催化的跟风补涨"]
    assert payload["after_hours_news"]["domestic_catalysts"] == ["机器人产业催化延续"]
    assert payload["capital_rotation"]["actual_path"][0] == "机器人承接"
    assert payload["capital_rotation"]["path_summary"] == "机器人承接 → PCB轮动 → 防御补位"
    assert payload["historical_theme_reviews"][0]["theme"] == "先进封装"
    assert payload["historical_theme_reviews"][0]["judgement"] == "降级观察"
    assert payload["historical_theme_reviews"][0]["current_stock_checks"] == ["长电科技 600584.SH 今日-3.20%"]
    assert payload["next_day_opportunity"]["focus_candidates"][0] == "机器人核心股承接"
    assert payload["practical_conclusion"]["headline"] == "明日重点是科技内部去弱留强。"
    assert payload["index_mid_term_outlook"]["scenario_table"][0]["scenario"] == "强势"


def _fake_report() -> ReportDTO:
    market = FakeMarketDataProvider()
    news = FakeNewsProvider()
    llm = FakeLLMProvider()
    snapshot = market.get_close_snapshot("2026-05-26")
    news_items = []
    for raw_sector in snapshot.raw_sectors:
        news_items.extend(news.search_sector_news(raw_sector.name, snapshot.trade_date))
    scored = score_sectors(snapshot.raw_sectors, top_n=5)
    return ReportDTO(
        trade_date=snapshot.trade_date,
        kind=ReportKind.CLOSE,
        title="2026-05-26 A股复盘",
        indices=snapshot.indices,
        breadth=snapshot.breadth,
        turnover_cny=snapshot.turnover_cny,
        market_state_tags=snapshot.market_state_tags,
        sectors=[
            SectorCandidate(
                name=sector.name,
                score=sector.score,
                rank=sector.rank,
                pct_change=sector.pct_change,
                reason="综合评分靠前",
                news_summaries=[item.summary for item in news_items if item.matched_sector == sector.name],
                factor_scores=sector.factor_scores,
            )
            for sector in scored
        ],
        narrative=llm.generate_narrative(snapshot.to_report_seed(news_items)),
        news=news_items,
    )


def test_build_structured_review_derives_core_modules_from_report() -> None:
    report = _fake_report()

    review = build_structured_review(report)

    assert review.topic == "放量分化 · 机器人领涨 · PCB轮动"
    assert review.prediction_review.source == "manual_placeholder"
    assert review.tomorrow_judgement.most_likely_to_continue == "机器人"
    assert review.tomorrow_judgement.most_likely_to_diverge == "PCB"
    assert review.market_overview.emotion_rows == [
        {"label": "上涨 / 下跌", "value": "3200 / 1800"},
        {"label": "涨停 / 跌停", "value": "86 / 8"},
        {"label": "成交额", "value": "12345.67 亿"},
    ]
    assert review.prediction_review.bias_reasons
    assert review.tomorrow_judgement.operating_focus
    assert review.market_overview.structure_notes
    assert review.sector_reviews[0].sector == "机器人"
    assert review.sector_reviews[0].logic_points
    assert review.sector_reviews[0].sustainability_analysis
    assert review.sector_reviews[0].sustainability == "high"
    assert review.sustainability_ranking[0].sector == "机器人"
    assert "机器人" in review.action_discipline.final_view
    assert review.after_hours_news.domestic_catalysts
    assert review.after_hours_news.risk_notes == ["消息与催化只作为明日观察线索，不作为单独决策依据。"]
    assert review.capital_rotation.actual_path[0] == "机器人承接"
    assert review.capital_rotation.path_summary == "机器人承接 → PCB轮动"
    assert "机器人" in review.capital_rotation.key_finding
    assert review.next_day_opportunity.focus_candidates[0] == "机器人核心股承接确认"
    assert "不追一致加速" in review.next_day_opportunity.position_discipline[0]
    assert review.practical_conclusion.headline.startswith("明日最实战")
    assert review.index_mid_term_outlook.scenario_table[0]["scenario"] == "强势延续"


def test_next_day_opportunity_lists_frontline_stock_codes_and_position_ranges() -> None:
    report = _fake_report()
    report.sectors[0].top_stocks = [
        StockCandidate(code="688690.SH", name="纳微科技", pct_change=12.36),
        StockCandidate(code="300672.SZ", name="国科微", pct_change=10.25),
    ]
    report.sectors[1].top_stocks = [
        StockCandidate(code="001299.SZ", name="美能能源", pct_change=10.01),
    ]

    review = build_structured_review(report)

    focus_text = "\n".join(review.next_day_opportunity.focus_candidates)
    position_text = "\n".join(review.next_day_opportunity.position_discipline)
    assert "纳微科技 688690.SH" in focus_text
    assert "国科微 300672.SZ" in focus_text
    assert "美能能源 001299.SZ" in focus_text
    assert "底仓" in position_text
    assert "2成" in position_text
    assert "3成" in position_text


def test_build_structured_review_prefers_highest_prediction_for_tomorrow_view() -> None:
    report = _fake_report()
    report.next_day_predictions = [
        NextDayPrediction(
            sector="PCB",
            rank=2,
            continuation_probability=76,
            confidence=PredictionConfidence.HIGH,
            headline="PCB延续概率较高，重点观察前排分歧承接。",
            front_row_stocks=[
                PredictionStockFocus(
                    code="300476.SZ",
                    name="胜宏科技",
                    pct_change=20.0,
                    role="前排强势股",
                    source_tags=["同花顺复盘", "东方财富涨停复盘"],
                    observation="观察胜宏科技竞价是否强于板块平均。",
                )
            ],
            trigger_conditions=["PCB前排分歧温和。"],
            invalidation_conditions=["PCB前排低开低走。"],
            risk_labels=["高位加速"],
        )
    ]

    review = build_structured_review(report)

    assert review.tomorrow_judgement.most_likely_to_continue == "PCB"
    assert review.next_day_opportunity.focus_candidates[0] == "胜宏科技 300476.SZ：观察胜宏科技竞价是否强于板块平均。"


def test_prediction_opportunity_candidates_include_stock_names_and_codes() -> None:
    report = _fake_report()
    report.next_day_predictions = [
        NextDayPrediction(
            sector="电力",
            rank=1,
            continuation_probability=82,
            confidence=PredictionConfidence.HIGH,
            headline="电力延续概率较高。",
            front_row_stocks=[
                PredictionStockFocus(
                    code="000539.SZ",
                    name="粤电力Ａ",
                    pct_change=10.04,
                    role="前排强势股",
                    source_tags=["TickFlow前排"],
                    observation="涨幅约10.04%，位于前排领涨位，观察竞价溢价与开盘承接，确认是否继续维持队形。",
                ),
                PredictionStockFocus(
                    code="001299.SZ",
                    name="美能能源",
                    pct_change=10.02,
                    role="前排强势股",
                    source_tags=["TickFlow前排"],
                    observation="涨幅约10.02%，位于前排同梯队，观察竞价溢价与开盘承接，确认是否继续维持队形。",
                ),
            ],
            trigger_conditions=["观察粤电力Ａ、美能能源竞价是否强于板块平均。"],
            invalidation_conditions=["前排股集体低开低走。"],
            risk_labels=[],
        )
    ]

    review = build_structured_review(report)
    focus_text = "\n".join(review.next_day_opportunity.focus_candidates)

    assert "粤电力Ａ 000539.SZ" in focus_text
    assert "美能能源 001299.SZ" in focus_text
    assert "观察竞价溢价与开盘承接" in focus_text


def test_structured_review_uses_distinct_leader_and_rotation_when_prediction_leader_differs() -> None:
    report = _fake_report()
    report.kind = ReportKind.MIDDAY
    report.sectors = [
        SectorCandidate(name="新材料", score=94, rank=1, pct_change=10.34, reason="综合评分靠前"),
        SectorCandidate(name="电力", score=92, rank=2, pct_change=10.0, reason="复盘源确认", review_sources=["同花顺复盘"]),
        SectorCandidate(name="半导体", score=90, rank=3, pct_change=13.87, reason="综合评分靠前"),
    ]
    report.next_day_predictions = [
        NextDayPrediction(
            sector="电力",
            rank=2,
            continuation_probability=94,
            confidence=PredictionConfidence.HIGH,
            headline="电力延续概率较高。",
            trigger_conditions=["观察电力前排承接。"],
            invalidation_conditions=["前排股集体低开低走。"],
            risk_labels=[],
        ),
        NextDayPrediction(
            sector="新材料",
            rank=1,
            continuation_probability=92,
            confidence=PredictionConfidence.HIGH,
            headline="新材料延续概率较高。",
            trigger_conditions=["观察新材料前排承接。"],
            invalidation_conditions=["前排股集体低开低走。"],
            risk_labels=[],
        ),
    ]

    review = build_structured_review(report)

    assert review.tomorrow_judgement.most_likely_to_continue == "电力"
    assert review.tomorrow_judgement.rotation_candidates[0] == "新材料"
    assert "围绕电力去弱留强，同时确认新材料是否具备持续性" in review.practical_conclusion.headline
    assert "电力与新材料之间的资金切换" in review.prediction_review.revision


def test_build_structured_review_tracks_previous_strong_themes() -> None:
    report = _fake_report()
    report.sectors = [
        SectorCandidate(
            name="电力",
            score=86.0,
            rank=1,
            pct_change=4.2,
            reason="今日强势",
            top_stocks=[StockCandidate(code="000539.SZ", name="粤电力Ａ", pct_change=10.04)],
            review_sources=["同花顺复盘"],
            review_notes=["电力方向前排强势。"],
        )
    ]
    report.previous_strong_themes = [
        HistoricalThemeReview(
            theme="先进封装",
            previous_status="昨日持续性高",
            current_status="今日未进入强势前排",
            judgement="降级观察",
            evidence=["昨日核心股：长电科技+10.00%、华天科技+10.00%"],
            watch_items=["观察长电科技、华天科技能否重新转强"],
        )
    ]

    review = build_structured_review(report)

    assert review.historical_theme_reviews[0].theme == "先进封装"
    assert review.historical_theme_reviews[0].judgement == "降级观察"
    assert "先进封装" in review.prediction_review.missed_items[0]
    assert "先进封装" in review.tomorrow_judgement.most_likely_to_diverge


def test_build_structured_review_keeps_news_evidence_compact() -> None:
    report = _fake_report()
    long_news = (
        "浦发银行(600000)\n"
        "9.27↑\n"
        "0.19 2.09%\n"
        "基本资料 公司全称 上海浦东发展银行股份有限公司 英文名称 Shanghai Pudong Development Bank Co.,Ltd. "
        "A股代码 600000 B股代码 -- H股代码 -- 证券类别 上交所主板A股 联系电话 021-63611226 传真 021-63230807"
    )
    report.sectors[0].news_summaries = [long_news]

    review = build_structured_review(report)

    evidence = review.sector_reviews[0].strengths[2]
    assert "\n" not in evidence
    assert len(evidence) <= 72
    assert "联系电话" not in evidence
class SuccessfulStructuredLLM:
    provider_name = "openai"

    def generate_structured_review(self, seed: dict[str, object]):
        review = build_structured_review(_fake_report())
        review.topic = "LLM生成 · 科技内部复盘"
        return review


class BrokenStructuredLLM:
    provider_name = "openai"

    def generate_structured_review(self, seed: dict[str, object]):
        raise LLMFallbackError("OPENAI_API_KEY 未配置")


def test_structured_review_generator_rule_mode_returns_rule_status() -> None:
    report = _fake_report()

    review, status = generate_structured_review(
        report=report,
        llm_provider=BrokenStructuredLLM(),
        provider_mode="rule",
        fallback_enabled=True,
    )

    assert review.topic == "放量分化 · 机器人领涨 · PCB轮动"
    assert status.model_dump(mode="json") == {
        "provider": "rule",
        "status": "success",
        "fallback_used": False,
        "reason": None,
    }


def test_structured_review_generator_llm_mode_uses_llm_on_success() -> None:
    report = _fake_report()

    review, status = generate_structured_review(
        report=report,
        llm_provider=SuccessfulStructuredLLM(),
        provider_mode="llm",
        fallback_enabled=True,
    )

    assert review.topic == "LLM生成 · 科技内部复盘"
    assert status.provider == "llm"
    assert status.status == "success"
    assert status.fallback_used is False


def test_structured_review_generator_falls_back_to_rule_on_llm_failure() -> None:
    report = _fake_report()

    review, status = generate_structured_review(
        report=report,
        llm_provider=BrokenStructuredLLM(),
        provider_mode="llm",
        fallback_enabled=True,
    )

    assert review.topic == "放量分化 · 机器人领涨 · PCB轮动"
    assert status.provider == "llm"
    assert status.status == "fallback"
    assert status.fallback_used is True
    assert status.reason == "OPENAI_API_KEY 未配置"


def test_structured_review_generator_can_raise_when_fallback_disabled() -> None:
    report = _fake_report()

    with pytest.raises(LLMFallbackError, match="OPENAI_API_KEY"):
        generate_structured_review(
            report=report,
            llm_provider=BrokenStructuredLLM(),
            provider_mode="llm",
            fallback_enabled=False,
        )

def test_structured_review_uses_front_row_stocks_and_review_sources_in_sector_analysis() -> None:
    report = _fake_report()
    report.sectors[0].name = "PCB"
    report.sectors[0].top_stocks = [
        StockCandidate(code="688183", name="生益电子", pct_change=20.0, tags=["同花顺复盘"]),
        StockCandidate(code="002552", name="宝鼎科技", pct_change=10.0, tags=["东方财富涨停复盘"]),
    ]
    report.sectors[0].review_sources = ["同花顺复盘", "东方财富涨停复盘"]
    report.sectors[0].review_notes = ["PCB概念股午后多数上扬，生益电子20cm涨停。"]

    review = build_structured_review(report)

    sector = review.sector_reviews[0]
    assert "生益电子" in "\n".join(sector.strengths)
    assert "同花顺复盘" in "\n".join(sector.logic_points)
    assert "前排" in sector.next_day_view
    assert review.practical_conclusion.headline.startswith("明日最实战")
