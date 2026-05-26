import json

import pytest

from app.providers.llm import LLMFallbackError, OpenAILLMProvider


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
            "revision": "继续观察科技内部轮动。",
            "source": "manual_placeholder",
        },
        "tomorrow_judgement": {
            "most_likely_to_continue": "机器人",
            "most_likely_to_diverge": "PCB",
            "rotation_candidates": ["PCB"],
            "defensive_candidates": ["高股息"],
            "core_view": "科技内部去弱留强。",
        },
        "market_overview": {
            "index_rows": [{"name": "上证指数", "close": "3100.50", "change": "+1.20%"}],
            "emotion_rows": [{"label": "涨停 / 跌停", "value": "86 / 8"}],
            "structure_features": ["放量", "分化"],
            "capital_flow_summary": "资金在科技方向内部切换。",
        },
        "sector_reviews": [
            {
                "sector": "机器人",
                "headline": "机器人：主线承接仍强",
                "stage": "主升延续",
                "strengths": ["涨幅居前"],
                "weaknesses": ["高位分歧"],
                "logic": "短线强度和消息催化共振。",
                "sustainability": "high",
                "next_day_view": "观察核心股承接。",
                "watch_items": ["回踩承接"],
                "avoid_items": ["缩量冲高"],
            }
        ],
        "sustainability_ranking": [
            {"rank": 1, "sector": "机器人", "rating": "high", "reason": "强度领先"}
        ],
        "action_discipline": {
            "focus": ["观察机器人核心方向"],
            "avoid": ["回避跟风补涨"],
            "final_view": "围绕机器人去弱留强。",
        },
    }


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
