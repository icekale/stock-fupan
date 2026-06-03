import pytest

from app.providers.llm import FakeLLMProvider, LLMFallbackError
from app.providers.market import FakeMarketDataProvider
from app.providers.news import FakeNewsProvider
from app.rules.scoring import score_sectors
from app.schemas.report import (
    DragonTigerStock,
    DragonTigerSummary,
    MarketBreadth,
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
    CapitalRotationReviewV2,
    HistoricalThemeReview,
    IndexMidTermOutlook,
    MarketPhaseReview,
    MarketOverviewTable,
    NextDayOpportunityPlan,
    NextSessionStrategy,
    PracticalConclusion,
    PredictionVerificationItem,
    PredictionReview,
    SectorDeepDive,
    StructuredReviewDTO,
    StructuredSectorReview,
    SustainabilityRank,
    TomorrowJudgement,
)
from app.services.structured_review_builder import build_structured_review
from app.services.structured_review_generator import generate_structured_review
from app.services.catalyst_summarizer import summarize_catalysts


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


def test_structured_review_serializes_v2_review_modules() -> None:
    review = StructuredReviewDTO(
        topic="V型反转 · 科技扩散",
        market_phase=MarketPhaseReview(
            phase="mainline_expansion",
            headline="科技主线从集中走向扩散",
            key_signal="电子方向资金从早盘净流出转为收盘净流入。",
            yesterday_today_compare=["昨日封测单点承压", "今日CPO/MLCC/散热多点修复"],
        ),
        prediction_review=PredictionReview(
            previous_prediction="昨日判断科技惯性下探后小幅修复。",
            actual_result="创业板午后强修复，CPO前排创出新高。",
            correct_items=["惯性下探方向正确"],
            missed_items=["低估午后修复强度"],
            bias_reasons=["被前一日恐慌情绪影响"],
            revision="后续重点看科技内部分支轮动，而非全面退潮。",
        ),
        prediction_verifications=[
            PredictionVerificationItem(
                claim="科技惯性下探后小幅修复",
                verdict="部分正确",
                actual_result="下探后强修复，修复力度超预期。",
                evidence=["创业板+1.96%", "CPO前排20cm涨停"],
                bias_reason="低估主线资金回流速度。",
            )
        ],
        tomorrow_judgement=TomorrowJudgement(
            most_likely_to_continue="CPO/光模块",
            most_likely_to_diverge="白酒/消费",
            core_view="明日看科技前排分歧承接。",
        ),
        market_overview=MarketOverviewTable(capital_flow_summary="缩量修复，资金仍偏谨慎。"),
        after_hours_news=AfterHoursNewsSummary(),
        sector_reviews=[],
        sector_deep_dives=[
            SectorDeepDive(
                sector="CPO/光模块",
                stage="new_leader",
                rating="high",
                catalysts=["海外光互连指引上调"],
                core_stocks=["联特科技", "中际旭创", "新易盛"],
                capital_evidence=["机构净买入约39亿"],
                team_structure="20cm领涨+中军创新高",
                conclusion="接棒成为科技新核心。",
                watch_signals=["前排分歧后继续承接"],
                avoid_signals=["一致加速追高"],
            )
        ],
        sustainability_ranking=[],
        capital_rotation=CapitalRotationPath(
            key_finding="科技资金从封测/存储扩散到CPO/MLCC。",
        ),
        capital_rotation_v2=CapitalRotationReviewV2(
            path=["半导体封测流出", "CPO回流", "MLCC扩散"],
            rotation_type="主线内部扩散",
            key_finding="不是科技全面退潮，而是AI算力链内部重分配。",
            next_watch=["CPO前排承接", "MLCC梯队完整度"],
        ),
        historical_theme_reviews=[],
        next_day_opportunity=NextDayOpportunityPlan(),
        next_session_strategy=NextSessionStrategy(
            focus=["CPO前排分歧承接"],
            observe=["MLCC是否从补涨转持续"],
            avoid=["白酒一日游后排"],
            trigger_conditions=["指数不放量下杀"],
            invalidation_conditions=["科技前排集体低开低走"],
        ),
        practical_conclusion=PracticalConclusion(headline="明日看科技前排承接"),
        index_mid_term_outlook=IndexMidTermOutlook(current_position="结构性修复"),
        action_discipline=ActionDiscipline(final_view="不追一致加速。"),
    )

    payload = review.model_dump(mode="json")

    assert payload["market_phase"]["phase"] == "mainline_expansion"
    assert payload["prediction_verifications"][0]["verdict"] == "部分正确"
    assert payload["sector_deep_dives"][0]["stage"] == "new_leader"
    assert payload["capital_rotation_v2"]["rotation_type"] == "主线内部扩散"
    assert payload["next_session_strategy"]["avoid"] == ["白酒一日游后排"]


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
    assert review.sector_reviews[0].sustainability == "medium"
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


def test_build_structured_review_adds_market_phase_with_specific_signal() -> None:
    report = _fake_report()
    report.breadth = MarketBreadth(up_count=3200, down_count=1800, limit_up_count=86, limit_down_count=8)
    report.market_state_tags = ["放量", "普涨"]
    report.sectors[0] = report.sectors[0].model_copy(update={"name": "机器人", "score": 82, "pct_change": 5.88})
    report.sectors[1] = report.sectors[1].model_copy(update={"name": "PCB", "score": 76, "pct_change": 3.60})

    review = build_structured_review(report)

    assert review.market_phase is not None
    assert review.market_phase.phase in {"repair", "structural_rebound", "mainline_expansion"}
    assert "机器人" in review.market_phase.headline
    assert "涨停86" in review.market_phase.key_signal
    assert review.market_phase.yesterday_today_compare


def test_build_structured_review_adds_itemized_prediction_verification() -> None:
    report = _fake_report()
    report.previous_strong_themes = [
        HistoricalThemeReview(
            theme="先进封装",
            previous_status="昨日强势前排",
            current_status="今日跌出前排",
            judgement="进入分歧",
            evidence=["长电科技走弱", "存储芯片资金流出"],
        )
    ]

    review = build_structured_review(report)

    assert review.prediction_verifications
    first = review.prediction_verifications[0]
    assert first.claim
    assert first.verdict in {"正确", "部分正确", "错误", "证据不足"}
    assert first.actual_result
    assert first.evidence


def test_build_structured_review_adds_sector_deep_dives_with_real_stocks() -> None:
    report = _fake_report()
    report.sectors[0] = report.sectors[0].model_copy(
        update={
            "name": "CPO/光模块",
            "score": 86,
            "pct_change": 5.4,
            "top_stocks": [
                StockCandidate(
                    code="300394.SZ",
                    name="联特科技",
                    pct_change=20.0,
                    turnover_cny=2_100_000_000,
                    turnover_rate=18.2,
                    tags=["TickFlow前排"],
                ),
                StockCandidate(
                    code="300308.SZ",
                    name="中际旭创",
                    pct_change=7.79,
                    turnover_cny=9_500_000_000,
                    turnover_rate=6.5,
                    tags=["TickFlow前排"],
                ),
            ],
            "news_summaries": ["海外光互连需求上调，带动CPO方向走强。"],
            "review_notes": ["同花顺复盘确认CPO为科技扩散方向。"],
        }
    )

    review = build_structured_review(report)

    assert review.sector_deep_dives
    cpo = review.sector_deep_dives[0]
    assert cpo.sector == "CPO/光模块"
    assert cpo.stage in {"leader", "new_leader", "branch_expansion"}
    assert "联特科技" in cpo.core_stocks
    assert cpo.capital_evidence
    assert cpo.conclusion
    assert cpo.watch_signals


def test_build_structured_review_uses_dragon_tiger_sentiment_and_sector_evidence() -> None:
    report = _fake_report()
    report.sectors[0] = report.sectors[0].model_copy(
        update={
            "name": "半导体",
            "score": 86,
            "pct_change": 5.4,
            "top_stocks": [
                StockCandidate(
                    code="002156.SZ",
                    name="通富微电",
                    pct_change=10.0,
                    turnover_cny=3_200_000_000,
                    turnover_rate=12.6,
                )
            ],
            "review_sources": ["同花顺复盘"],
            "review_notes": ["同花顺复盘确认半导体前排扩散。"],
        }
    )
    report.dragon_tiger = DragonTigerSummary(
        trade_date=report.trade_date,
        total_records=91,
        positive_net_count=55,
        negative_net_count=36,
        net_buy_total_wan=268081.1,
        mainline_match_count=2,
        mainline_match_names=["通富微电", "亨通光电"],
        sentiment="strong",
        strength="high",
        top_net_buy=[
            DragonTigerStock(code="002156", name="通富微电", net_buy_wan=162241.5),
            DragonTigerStock(code="600487", name="亨通光电", net_buy_wan=84125.3),
        ],
    )

    review = build_structured_review(report)

    assert {"label": "龙虎榜", "value": "强 / high"} in review.market_overview.emotion_rows
    assert "龙虎榜净买集中在通富微电、亨通光电" in review.market_overview.capital_flow_summary
    semiconductor = next(item for item in review.sector_deep_dives if item.sector == "半导体")
    assert any("龙虎榜确认" in item and "通富微电" in item for item in semiconductor.capital_evidence)
    semiconductor_rank = next(item for item in review.sustainability_ranking if item.sector == "半导体")
    assert "龙虎榜" in semiconductor_rank.reason


def test_build_structured_review_does_not_apply_dragon_tiger_matches_to_unrelated_sectors() -> None:
    report = _fake_report()
    report.sectors = [
        SectorCandidate(
            name="半导体",
            score=86,
            rank=1,
            pct_change=5.4,
            reason="综合评分靠前",
            top_stocks=[StockCandidate(code="002156.SZ", name="通富微电", pct_change=10.0)],
            review_sources=["同花顺复盘"],
            review_notes=["同花顺复盘确认半导体前排扩散。"],
        ),
        SectorCandidate(
            name="电力",
            score=74,
            rank=2,
            pct_change=2.2,
            reason="轮动观察",
            top_stocks=[StockCandidate(code="000539.SZ", name="粤电力Ａ", pct_change=10.04)],
            review_sources=["同花顺复盘"],
            review_notes=["同花顺复盘确认电力轮动。"],
        ),
    ]
    report.dragon_tiger = DragonTigerSummary(
        trade_date=report.trade_date,
        mainline_match_names=["通富微电"],
        sentiment="strong",
        strength="high",
        top_net_buy=[DragonTigerStock(code="002156", name="通富微电", net_buy_wan=162241.5)],
    )

    review = build_structured_review(report)

    power = next(item for item in review.sector_deep_dives if item.sector == "电力")
    assert not any("龙虎榜确认" in item for item in power.capital_evidence)
    power_rank = next(item for item in review.sustainability_ranking if item.sector == "电力")
    assert "龙虎榜" not in power_rank.reason


def test_build_structured_review_localizes_medium_dragon_tiger_sentiment() -> None:
    report = _fake_report()
    report.dragon_tiger = DragonTigerSummary(
        trade_date=report.trade_date,
        sentiment="medium",
        strength="normal",
        top_net_buy=[DragonTigerStock(code="002156", name="通富微电", net_buy_wan=162241.5)],
    )

    review = build_structured_review(report)

    assert {"label": "龙虎榜", "value": "中 / normal"} in review.market_overview.emotion_rows


def test_build_structured_review_adds_v2_capital_rotation_and_strategy() -> None:
    report = _fake_report()
    report.sectors[0] = report.sectors[0].model_copy(update={"name": "CPO/光模块", "score": 86})
    report.sectors[1] = report.sectors[1].model_copy(update={"name": "MLCC/被动元件", "score": 74})
    report.previous_strong_themes = [
        HistoricalThemeReview(
            theme="半导体封测/存储",
            previous_status="昨日强势",
            current_status="今日跌出前排",
            judgement="进入分歧",
            evidence=["长电科技走弱"],
        )
    ]

    review = build_structured_review(report)

    assert review.capital_rotation_v2 is not None
    assert review.capital_rotation_v2.path[0].startswith("半导体封测/存储")
    assert "CPO/光模块" in " → ".join(review.capital_rotation_v2.path)
    assert review.next_session_strategy is not None
    assert any("CPO/光模块" in item for item in review.next_session_strategy.focus)
    assert review.next_session_strategy.avoid


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


def test_build_structured_review_summarizes_deep_dive_catalysts() -> None:
    report = _fake_report()
    report.sectors[0] = report.sectors[0].model_copy(
        update={
            "name": "电力",
            "news_summaries": [
                "A股电力板块反复活跃 华电能源2连板、京能电力等跟涨 2026年05月29日 18:30 财经网站转载，电力板块低开高走，晋控电力、华能国际、山南电A、粤电力A、华能蒙电等多股涨停，珈伟新能涨超11%，板块资金回流明显。"
            ],
            "review_notes": [
                "THSDK问财今日涨停返回67条前排样例",
                "THSDK问财今日连板返回16条高度样例",
            ],
        }
    )

    review = build_structured_review(report)

    catalysts = review.sector_deep_dives[0].catalysts
    assert len(catalysts) <= 2
    assert all(len(item) <= 36 for item in catalysts)
    assert not any("晋控电力、华能国际、山南电A、粤电力A、华能蒙电" in item for item in catalysts)
    assert not any("2026年" in item or "18:30" in item or "财经网站" in item for item in catalysts)
    assert "问财确认67条涨停前排，板块扩散强" in catalysts
    assert "问财确认16条连板高度，留意前排承接" in catalysts


class CatalystSummaryLLM:
    def summarize_catalysts(self, sector_name: str, evidence: list[str]) -> list[str]:
        assert sector_name == "电力"
        assert evidence
        return ["AI摘要：电力前排涨停", "AI摘要：连板高度确认"]


class BrokenCatalystSummaryLLM:
    def summarize_catalysts(self, sector_name: str, evidence: list[str]) -> list[str]:
        return ["政策端形成'顶层设计+资金支", "资金支持+税收优惠'的全"]


def test_catalyst_summarizer_prefers_ai_when_available() -> None:
    result = summarize_catalysts(
        ["电力板块低开高走，晋控电力、华能国际、粤电力A等多股涨停。"],
        sector_name="电力",
        llm_provider=CatalystSummaryLLM(),
    )

    assert result == ["AI摘要：电力前排涨停", "AI摘要：连板高度确认"]


def test_catalyst_summarizer_rejects_truncated_ai_fragments() -> None:
    result = summarize_catalysts(
        ["Anspire新闻：半导体多股涨停，资金持续回流 2026年06月02日 18:30 财联社。"],
        sector_name="半导体",
        trade_date="2026-06-02",
        llm_provider=BrokenCatalystSummaryLLM(),
    )

    assert result == ["多股涨停，资金回流，前排强度明确"]


def test_catalyst_summarizer_avoids_truncated_policy_fragments() -> None:
    result = summarize_catalysts(
        [
            (
                "骑牛看熊 2026年06月01日 11:50 湖北 "
                "半导体板块近期的连续上涨并非短期炒作，"
                "政策端形成'顶层设计+资金支持+税收优惠'的全方位支撑体系，"
                "国产替代提速、AI需求爆发、资金流入五大因素共振。"
            )
        ],
        sector_name="半导体",
        trade_date="2026-06-02",
    )

    assert result == ["政策全方位支撑，国产替代与AI需求共振"]


def test_catalyst_summarizer_drops_generic_listicle_titles() -> None:
    result = summarize_catalysts(
        [
            "Anspire新闻：2026年机器人龙头股名单一览，机器人概念上市公司股票有哪些？",
            "Anspire新闻：机器人概念有望翻倍，相关股票名录请收藏",
        ],
        sector_name="机器人",
    )

    assert result == ["消息面仅作观察，缺少明确催化"]


def test_catalyst_summarizer_extracts_compact_logic_from_news() -> None:
    result = summarize_catalysts(
        [
            "Anspire新闻：AI服务器升级打开产业空间 A股PCB概念股强势 生益电子、生益科技等多股涨停，资金持续回流。",
            "Anspire新闻：半导体板块全产业链多点开花，24只半导体股创新高，先进封装、存储芯片方向活跃。",
        ],
        sector_name="PCB",
    )

    assert result == ["AI服务器升级打开产业空间，PCB获资金确认", "多股涨停，资金回流，前排强度明确"]
    assert all(16 <= len(item) <= 24 for item in result)
    assert not any("Anspire" in item or "概念股强势" in item for item in result)


def test_catalyst_summarizer_uses_fallback_for_weak_headlines() -> None:
    result = summarize_catalysts(
        [
            "Anspire新闻：环保服务行业公司助力＂碳中和＂，12只有望翻倍龙头一览 环保概念风口来了。",
            "Anspire新闻：环保行业周报：生态补偿+大气防治 环境监测迎需求共振 11:15 和讯。",
            "Anspire新闻：风格突变！002491，垂直涨停！新能源、新材料，涨涨涨！",
            "Anspire新闻：收评：三大指数集体下跌 半导体、MicroLED、金属新材料跌幅居前。",
        ],
        sector_name="环保",
    )

    assert result == ["消息面仅作观察，缺少明确催化"]


def test_catalyst_summarizer_filters_stale_or_undated_headlines() -> None:
    result = summarize_catalysts(
        [
            "Anspire新闻：A股新材料概念股整理!(3/25) 南方财富网 2026-04-25 14:03 截至4月25日，新材料概念股名单。",
            "Anspire新闻：A股收评：三大指数集体下跌 半导体、MicroLED、金属新材料跌幅居前 2026年05月29日 15:20。",
            "Anspire新闻：新材料多股涨停，资金持续回流 2026年06月02日 18:30 财联社。",
            "Anspire新闻：球形硅微粉：全球缺口扩大，高端缺口显著。",
        ],
        sector_name="新材料",
        trade_date="2026-06-02",
    )

    assert result == ["多股涨停，资金回流，前排强度明确"]


def test_catalyst_summarizer_rejects_future_article_even_when_body_mentions_trade_date() -> None:
    result = summarize_catalysts(
        [
            "Anspire新闻：半导体产业链继续反弹 2026-06-03 13:04 发布，截至2026年6月2日，半导体设备ETF近1月累计上涨。"
        ],
        sector_name="半导体",
        trade_date="2026-06-02",
    )

    assert result == ["消息面仅作观察，缺少明确催化"]


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


def test_structured_review_applies_hard_evidence_gates_and_limits_deep_dives() -> None:
    report = _fake_report()
    report.trade_date = "2026-06-02"
    report.sectors = [
        SectorCandidate(
            name="新材料",
            score=86,
            rank=1,
            pct_change=10.44,
            reason="综合评分靠前",
            top_stocks=[
                StockCandidate(code="300398.SZ", name="飞凯材料", pct_change=20.0, turnover_cny=2_115_000_000),
                StockCandidate(code="603330.SH", name="天洋新材", pct_change=10.0, turnover_cny=68_000_000),
                StockCandidate(code="002171.SZ", name="楚江新材", pct_change=9.9, turnover_cny=1_241_000_000),
                StockCandidate(code="002171.SZ", name="楚江新材", pct_change=9.9, turnover_cny=1_241_000_000),
            ],
            news_summaries=[
                "Anspire新闻：A股新材料概念股整理!(3/25) 南方财富网 2026-04-25 14:03 截至4月25日。",
            "Anspire新闻：新材料多股涨停，资金持续回流 2026年06月02日 18:30 财联社。",
            ],
            review_sources=["同花顺复盘"],
            review_notes=["同花顺复盘确认新材料前排扩散。"],
            capital_evidence=report.sectors[0].capital_evidence,
        ),
        SectorCandidate(
            name="半导体",
            score=73,
            rank=2,
            pct_change=5.2,
            reason="轮动强度靠前",
            top_stocks=[StockCandidate(code="688008.SH", name="澜起科技", pct_change=8.0)],
            news_summaries=["Anspire新闻：半导体ETF开盘涨0.33%，重仓股表现分化。"],
        ),
        SectorCandidate(
            name="环保",
            score=57,
            rank=3,
            pct_change=2.1,
            reason="修复观察",
            news_summaries=["Anspire新闻：环保行业周报：城市更新规划 生态修复获政策加码 2026-06-01 08:00。"],
        ),
        SectorCandidate(name="机器人", score=54, rank=4, pct_change=1.5, reason="价格异动"),
    ]

    review = build_structured_review(report)

    deep_dives = review.sector_deep_dives
    assert [item.sector for item in deep_dives] == ["新材料", "半导体"]
    assert deep_dives[0].rating == "high"
    assert deep_dives[1].rating == "medium"
    assert deep_dives[0].catalysts == ["多股涨停，资金回流，前排强度明确"]
    assert deep_dives[0].core_stocks == ["飞凯材料", "天洋新材", "楚江新材"]
    assert all(len(item.catalysts) <= 3 for item in deep_dives)
    assert all(len(item.core_stocks) <= 3 for item in deep_dives)
    assert all(len(item.watch_signals) <= 3 for item in deep_dives)
    assert all(len(item.avoid_signals) <= 2 for item in deep_dives)
    assert not any("概念股整理" in item for item in deep_dives[0].catalysts)
    assert review.sustainability_ranking[1].rating == "medium"
    assert review.sustainability_ranking[2].rating == "low"
