import pytest

from app.providers.llm import FakeLLMProvider, LLMFallbackError
from app.providers.market import FakeMarketDataProvider
from app.providers.news import FakeNewsProvider
from app.rules.scoring import score_sectors
from app.schemas.report import ReportDTO, ReportKind, SectorCandidate
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
            revision="明日观察机器人与PCB之间的资金切换。",
            source="manual_placeholder",
        ),
        tomorrow_judgement=TomorrowJudgement(
            most_likely_to_continue="机器人",
            most_likely_to_diverge="PCB",
            rotation_candidates=["PCB"],
            defensive_candidates=["高股息"],
            core_view="主线仍在科技内部轮动，去弱留强。",
        ),
        market_overview=MarketOverviewTable(
            index_rows=[{"name": "上证指数", "close": "3100.50", "change": "+1.20%"}],
            emotion_rows=[{"label": "涨停 / 跌停", "value": "86 / 8"}],
            structure_features=["放量", "分化"],
            capital_flow_summary="资金集中在科技方向内部轮动。",
        ),
        after_hours_news=AfterHoursNewsSummary(
            us_market_mapping=["英伟达链条映射仍需观察"],
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
            key_finding="科技内部仍是资金轮动主场。",
            next_path_watch=["观察机器人分歧后是否回流", "观察PCB是否继续扩散"],
        ),
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
    assert review.sector_reviews[0].sector == "机器人"
    assert review.sector_reviews[0].sustainability == "high"
    assert review.sustainability_ranking[0].sector == "机器人"
    assert "机器人" in review.action_discipline.final_view
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
