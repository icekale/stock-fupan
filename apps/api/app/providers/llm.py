from typing import Protocol

from app.schemas.report import ReportNarrative
from app.schemas.structured_review import StructuredReviewDTO


class LLMProvider(Protocol):
    def generate_narrative(self, seed: dict[str, object]) -> ReportNarrative:
        raise NotImplementedError

    def generate_structured_review(self, seed: dict[str, object]) -> StructuredReviewDTO:
        raise NotImplementedError


class FakeLLMProvider:
    def generate_narrative(self, seed: dict[str, object]) -> ReportNarrative:
        return ReportNarrative(
            conclusion="上证指数上涨1.2%，市场放量分化，机器人是今日主线。",
            overview="两市涨停86只，成交额12345.67亿元。",
            sector_commentary=["机器人板块涨幅5.88%，短线强度居前。"],
            watchlist=["关注机器人核心股承接。"],
            tomorrow="明日观察机器人方向分歧后的承接。",
            risks=["涨停86只后高位分歧可能加大。"],
        )

    def generate_structured_review(self, seed: dict[str, object]) -> StructuredReviewDTO:
        from app.services.structured_review_builder import build_structured_review_from_seed

        return build_structured_review_from_seed(seed)


class LLMFallbackError(RuntimeError):
    pass


class OpenAILLMProvider:
    provider_name = "openai"

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model_name: str,
        client: object | None = None,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url
        self.model_name = model_name
        self.client = client

    def generate_narrative(self, seed: dict[str, object]) -> ReportNarrative:
        return FakeLLMProvider().generate_narrative(seed)

    def generate_structured_review(self, seed: dict[str, object]) -> StructuredReviewDTO:
        raise LLMFallbackError("OpenAI structured review generation not implemented")
