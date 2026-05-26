from typing import Protocol

from app.schemas.report import ReportNarrative


class LLMProvider(Protocol):
    def generate_narrative(self, seed: dict[str, object]) -> ReportNarrative:
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
