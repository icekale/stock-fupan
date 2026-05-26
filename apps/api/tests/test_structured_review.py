from app.schemas.structured_review import (
    ActionDiscipline,
    MarketOverviewTable,
    PredictionReview,
    StructuredReviewDTO,
    StructuredSectorReview,
    SustainabilityRank,
    TomorrowJudgement,
)


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
