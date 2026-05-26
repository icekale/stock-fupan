import json
from typing import Protocol

from openai import OpenAI
from pydantic import ValidationError

from app.schemas.report import ReportNarrative
from app.schemas.structured_review import StructuredReviewDTO


STRUCTURED_REVIEW_SYSTEM_PROMPT = """你是A股盘后复盘助手。只基于用户提供的结构化事实生成 JSON。
不得编造未提供的数字、板块、个股、新闻来源。
没有前一日报告时 prediction_review.source 必须为 manual_placeholder。
必须输出完整 StructuredReviewDTO 字段，包括 after_hours_news、capital_rotation、next_day_opportunity、practical_conclusion、index_mid_term_outlook。
所有买卖建议必须改写为观察条件、风险分层、仓位纪律、回避清单。
不要使用确定性荐股语气，不要承诺收益。
输出必须是合法 JSON，且字段匹配 StructuredReviewDTO。"""


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


def _safe_error(prefix: str, exc: Exception) -> str:
    return f"{prefix}: {exc.__class__.__name__}"


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
        if not self.api_key:
            raise LLMFallbackError("OPENAI_API_KEY 未配置")

        client = self.client or OpenAI(api_key=self.api_key, base_url=self.base_url)
        try:
            completion = client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": STRUCTURED_REVIEW_SYSTEM_PROMPT},
                    {"role": "user", "content": json.dumps(seed, ensure_ascii=False)},
                ],
                response_format={"type": "json_object"},
                temperature=0.2,
            )
            content = completion.choices[0].message.content
        except Exception as exc:
            raise LLMFallbackError(_safe_error("OpenAI 请求失败", exc)) from exc

        if not content:
            raise LLMFallbackError("OpenAI 返回空内容")
        try:
            payload = json.loads(content)
        except json.JSONDecodeError as exc:
            raise LLMFallbackError("OpenAI JSON 解析失败") from exc
        try:
            return StructuredReviewDTO.model_validate(payload)
        except ValidationError as exc:
            raise LLMFallbackError("OpenAI 结构化复盘字段校验失败") from exc
