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
        indices = _list_of_dicts(seed.get("indices"))
        breadth = seed.get("breadth") if isinstance(seed.get("breadth"), dict) else {}
        sectors = _list_of_dicts(seed.get("raw_sectors"))
        tags = [str(tag) for tag in seed.get("market_state_tags", []) if str(tag)]
        turnover = _to_float(seed.get("turnover_cny"), 0.0)
        review_window = str(seed.get("review_window") or "明日")

        leading_sector = sectors[0] if sectors else {}
        leading_sector_name = str(leading_sector.get("name") or "暂无明确主线")
        leading_sector_change = _to_float(leading_sector.get("pct_change"), 0.0)
        first_index = indices[0] if indices else {}
        first_index_name = str(first_index.get("name") or "核心指数")
        first_index_close = _to_float(first_index.get("close"), 0.0)
        first_index_change = _to_float(first_index.get("pct_change"), 0.0)
        up_count = _to_int(breadth.get("up_count") if isinstance(breadth, dict) else None, 0)
        down_count = _to_int(breadth.get("down_count") if isinstance(breadth, dict) else None, 0)
        limit_up_count = _to_int(
            breadth.get("limit_up_count") if isinstance(breadth, dict) else None,
            0,
        )
        limit_down_count = _to_int(
            breadth.get("limit_down_count") if isinstance(breadth, dict) else None,
            0,
        )
        tag_text = "、".join(tags) if tags else "结构性分化"

        return ReportNarrative(
            conclusion=(
                f"{first_index_name}收于{first_index_close:.2f}点，涨跌幅{first_index_change:+.2f}%，"
                f"市场呈现{tag_text}特征，{leading_sector_name}相对靠前。"
            ),
            overview=(
                f"两市上涨{up_count}家、下跌{down_count}家，涨停{limit_up_count}只、"
                f"跌停{limit_down_count}只，成交额{turnover:.2f}亿元。"
            ),
            sector_commentary=[
                _build_sector_commentary(sector)
                for sector in sectors[:3]
            ],
            watchlist=[
                f"观察{leading_sector_name}方向在涨幅{leading_sector_change:+.2f}%后的承接强度。"
            ],
            tomorrow=(
                f"{review_window}优先观察{leading_sector_name}是否继续获得资金承接，"
                "同时留意高位分歧后的轮动方向。"
            ),
            risks=[
                f"市场已有{limit_up_count}只涨停，若缩量加速需防范一致性分歧。",
                f"跌停{limit_down_count}只仍提示局部风险，弱势方向不宜盲目接力。",
            ],
        )

    def generate_structured_review(self, seed: dict[str, object]) -> StructuredReviewDTO:
        from app.services.structured_review_builder import build_structured_review_from_seed

        return build_structured_review_from_seed(seed)


class LLMFallbackError(RuntimeError):
    pass


def _safe_error(prefix: str, exc: Exception) -> str:
    return f"{prefix}: {exc.__class__.__name__}"


def _list_of_dicts(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _to_float(value: object, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _to_int(value: object, default: int) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _build_sector_commentary(sector: dict[str, object]) -> str:
    sector_name = str(sector.get("name") or "未命名板块")
    pct_change = _to_float(sector.get("pct_change"), 0.0)
    return f"{sector_name}涨跌幅{pct_change:+.2f}%，短线强度相对靠前。"


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
