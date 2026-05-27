import json

import pytest

from app.providers.llm import FakeLLMProvider, LLMFallbackError, OpenAILLMProvider


class FakeMessage:
    def __init__(self, content: str) -> None:
        self.content = content


class FakeChoice:
    def __init__(self, content: str) -> None:
        self.message = FakeMessage(content)


class FakeCompletion:
    def __init__(self, content: str) -> None:
        self.choices = [FakeChoice(content)]


class FakeCompletions:
    def __init__(self, content: str | None = None, error: Exception | None = None) -> None:
        self.content = content
        self.error = error
        self.last_kwargs: dict[str, object] = {}

    def create(self, **kwargs: object) -> FakeCompletion:
        self.last_kwargs = kwargs
        if self.error is not None:
            raise self.error
        if self.content is None:
            raise RuntimeError("missing fake content")
        return FakeCompletion(self.content)


class FakeChat:
    def __init__(self, completions: FakeCompletions) -> None:
        self.completions = completions


class FakeClient:
    def __init__(self, completions: FakeCompletions) -> None:
        self.chat = FakeChat(completions)


def _valid_structured_payload() -> dict[str, object]:
    return {
        "topic": "科技内部淘汰赛 · 主线换挡日",
        "prediction_review": {
            "previous_prediction": "昨日预判机器人方向有分歧承接。",
            "actual_result": "机器人方向继续领涨。",
            "correct_items": ["机器人延续强势"],
            "missed_items": ["PCB强度略超预期"],
            "bias_reasons": ["昨日对PCB轮动估计偏保守"],
            "revision": "继续观察科技内部轮动。",
            "source": "manual_placeholder",
        },
        "tomorrow_judgement": {
            "most_likely_to_continue": "机器人",
            "most_likely_to_diverge": "PCB",
            "rotation_candidates": ["PCB"],
            "defensive_candidates": ["高股息"],
            "core_view": "科技内部去弱留强。",
            "operating_focus": ["先看机器人承接", "再看PCB扩散"],
        },
        "market_overview": {
            "index_rows": [{"name": "上证指数", "close": "3100.50", "change": "+1.20%"}],
            "emotion_rows": [{"label": "涨停 / 跌停", "value": "86 / 8"}],
            "structure_features": ["放量", "分化"],
            "structure_notes": ["科技内部强弱分化"],
            "capital_flow_summary": "资金在科技方向内部切换。",
        },
        "after_hours_news": {
            "us_market_mapping": ["海外科技链条反馈仍需观察"],
            "us_market_conclusion": "海外映射只作为观察线索。",
            "domestic_catalysts": ["机器人产业催化延续"],
            "risk_notes": ["盘后消息只作为次日观察线索"],
        },
        "sector_reviews": [
            {
                "sector": "机器人",
                "headline": "机器人：主线承接仍强",
                "stage": "主升延续",
                "strengths": ["涨幅居前"],
                "weaknesses": ["高位分歧"],
                "logic": "短线强度和消息催化共振。",
                "logic_points": ["涨幅居前", "新闻催化明确"],
                "sustainability_analysis": "主线承接仍强，但高位分歧需要观察。",
                "sustainability": "high",
                "next_day_view": "观察核心股承接。",
                "watch_items": ["回踩承接"],
                "avoid_items": ["缩量冲高"],
            }
        ],
        "sustainability_ranking": [
            {"rank": 1, "sector": "机器人", "rating": "high", "reason": "强度领先"}
        ],
        "capital_rotation": {
            "actual_path": ["机器人承接", "PCB轮动"],
            "path_summary": "机器人承接 → PCB轮动",
            "key_finding": "资金仍在科技内部切换。",
            "next_path_watch": ["观察机器人分歧后回流", "观察PCB扩散质量"],
        },
        "next_day_opportunity": {
            "focus_candidates": ["机器人核心股承接确认"],
            "position_discipline": ["不追一致加速"],
            "trigger_conditions": ["指数不放量下杀"],
            "avoid_conditions": ["缩量冲高回落"],
        },
        "practical_conclusion": {
            "headline": "明日围绕机器人去弱留强。",
            "bullet_points": ["先看承接", "再看轮动"],
        },
        "index_mid_term_outlook": {
            "year_review": ["指数仍是结构行情载体"],
            "current_position": "当前位置观察量能和主线扩散。",
            "scenario_table": [
                {"scenario": "强势延续", "condition": "放量上行", "response": "观察扩散"}
            ],
        },
        "action_discipline": {
            "focus": ["观察机器人核心方向"],
            "avoid": ["回避跟风补涨"],
            "final_view": "围绕机器人去弱留强。",
        },
    }


def test_fake_llm_narrative_is_derived_from_seed_facts() -> None:
    provider = FakeLLMProvider()
    narrative = provider.generate_narrative(
        {
            "trade_date": "2026-05-27",
            "indices": [
                {"name": "上证指数", "code": "000001", "close": 3350.12, "pct_change": -0.42},
                {"name": "创业板指", "code": "399006", "close": 2201.3, "pct_change": 1.18},
            ],
            "breadth": {
                "up_count": 2810,
                "down_count": 2190,
                "limit_up_count": 54,
                "limit_down_count": 12,
            },
            "turnover_cny": 9876.54,
            "market_state_tags": ["分化", "缩量"],
            "raw_sectors": [
                {
                    "name": "半导体",
                    "pct_change": 4.32,
                    "limit_up_count": 6,
                    "stock_up_ratio": 0.76,
                    "turnover_change": 0.28,
                    "news_weight": 0.7,
                },
                {
                    "name": "银行",
                    "pct_change": -1.15,
                    "limit_up_count": 0,
                    "stock_up_ratio": 0.25,
                    "turnover_change": -0.08,
                    "news_weight": 0.2,
                },
            ],
            "news": [
                {
                    "title": "半导体设备订单改善",
                    "summary": "半导体产业链订单边际改善。",
                    "matched_sector": "半导体",
                }
            ],
        }
    )

    full_text = "\n".join(
        [
            narrative.conclusion,
            narrative.overview,
            *narrative.sector_commentary,
            *narrative.watchlist,
            narrative.tomorrow,
            *narrative.risks,
        ]
    )
    assert "半导体" in full_text
    assert "机器人" not in full_text
    assert "3350.12" in full_text
    assert "9876.54" in full_text
    assert "54" in narrative.overview


def test_openai_llm_provider_maps_json_to_structured_review() -> None:
    completions = FakeCompletions(json.dumps(_valid_structured_payload(), ensure_ascii=False))
    provider = OpenAILLMProvider(
        api_key="sk-test-local",
        base_url="https://api.openai.com/v1",
        model_name="gpt-4.1-mini",
        client=FakeClient(completions),
    )

    review = provider.generate_structured_review({"trade_date": "2026-05-26"})

    assert review.topic == "科技内部淘汰赛 · 主线换挡日"
    assert review.sector_reviews[0].sector == "机器人"
    assert review.capital_rotation.actual_path == ["机器人承接", "PCB轮动"]
    assert completions.last_kwargs["model"] == "gpt-4.1-mini"
    assert completions.last_kwargs["response_format"] == {"type": "json_object"}


def test_openai_llm_provider_rejects_missing_key() -> None:
    provider = OpenAILLMProvider(api_key="", base_url="https://api.openai.com/v1", model_name="gpt-4.1-mini")

    with pytest.raises(LLMFallbackError, match="OPENAI_API_KEY"):
        provider.generate_structured_review({"trade_date": "2026-05-26"})


def test_openai_llm_provider_sanitizes_errors() -> None:
    leaked_key = "sk-secret-leak"
    provider = OpenAILLMProvider(
        api_key=leaked_key,
        base_url="https://api.openai.com/v1",
        model_name="gpt-4.1-mini",
        client=FakeClient(FakeCompletions(error=RuntimeError(f"boom {leaked_key}"))),
    )

    with pytest.raises(LLMFallbackError) as exc_info:
        provider.generate_structured_review({"trade_date": "2026-05-26"})

    message = str(exc_info.value)
    assert "OpenAI 请求失败" in message
    assert leaked_key not in message
