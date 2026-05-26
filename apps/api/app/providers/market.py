from dataclasses import asdict, dataclass
from datetime import date
import math
from types import ModuleType
from typing import Literal, Protocol

from pydantic import BaseModel

from app.rules.scoring import RawSectorInput
from app.schemas.report import IndexSnapshot, MarketBreadth, NewsItem


ProviderState = Literal["success", "fallback", "disabled", "failed"]


class ProviderStatus(BaseModel):
    provider: str
    status: ProviderState
    fallback_used: bool = False
    reason: str | None = None


class ProviderFallbackError(RuntimeError):
    pass


def _provider_name(provider: object, default: str) -> str:
    value = getattr(provider, "provider_name", default)
    return value if isinstance(value, str) and value else default


def _to_float(value: object, default: float | None = None) -> float:
    try:
        if value is None:
            raise TypeError
        number = float(value)
    except (TypeError, ValueError):
        if default is None:
            raise ProviderFallbackError("AkShare 返回了非数字字段")
        return default
    if not math.isfinite(number):
        if default is None:
            raise ProviderFallbackError("AkShare 返回了非数字字段")
        return default
    return number


def _pick(row: object, *names: str) -> object:
    for name in names:
        try:
            value = row[name]
        except Exception:
            continue
        if value is not None:
            return value
    raise ProviderFallbackError(f"AkShare 缺少字段: {'/'.join(names)}")


@dataclass(frozen=True)
class MarketCloseSnapshot:
    trade_date: str
    indices: list[IndexSnapshot]
    breadth: MarketBreadth
    turnover_cny: float
    market_state_tags: list[str]
    raw_sectors: list[RawSectorInput]

    def to_report_seed(self, news: list[NewsItem]) -> dict[str, object]:
        return {
            "trade_date": self.trade_date,
            "indices": [index.model_dump() for index in self.indices],
            "breadth": self.breadth.model_dump(),
            "turnover_cny": self.turnover_cny,
            "market_state_tags": self.market_state_tags,
            "raw_sectors": [asdict(sector) for sector in self.raw_sectors],
            "news": [item.model_dump() for item in news],
        }


class MarketDataProvider(Protocol):
    def get_close_snapshot(self, trade_date: str) -> MarketCloseSnapshot:
        raise NotImplementedError


class FakeMarketDataProvider:
    def get_close_snapshot(self, trade_date: str) -> MarketCloseSnapshot:
        return MarketCloseSnapshot(
            trade_date=trade_date,
            indices=[
                IndexSnapshot(name="上证指数", code="000001", close=3100.5, pct_change=1.2),
                IndexSnapshot(name="创业板指", code="399006", close=1950.2, pct_change=2.1),
            ],
            breadth=MarketBreadth(
                up_count=3200,
                down_count=1800,
                limit_up_count=86,
                limit_down_count=8,
            ),
            turnover_cny=12345.67,
            market_state_tags=["放量", "分化"],
            raw_sectors=[
                RawSectorInput(
                    name="机器人",
                    pct_change=5.88,
                    limit_up_count=8,
                    stock_up_ratio=0.82,
                    turnover_change=0.35,
                    news_weight=0.8,
                ),
                RawSectorInput(
                    name="PCB",
                    pct_change=3.6,
                    limit_up_count=4,
                    stock_up_ratio=0.7,
                    turnover_change=0.2,
                    news_weight=0.5,
                ),
            ],
        )


class AkShareMarketDataProvider:
    provider_name = "akshare"

    def __init__(self, akshare_module: ModuleType | object | None = None, today: date | None = None) -> None:
        self.akshare_module = akshare_module
        self.today = today

    def _akshare(self) -> ModuleType | object:
        if self.akshare_module is not None:
            return self.akshare_module
        import akshare as ak

        return ak

    def get_close_snapshot(self, trade_date: str) -> MarketCloseSnapshot:
        current_date = self.today or date.today()
        if trade_date != current_date.isoformat():
            raise ProviderFallbackError("AkShare v0.2 暂不支持历史日期")

        try:
            ak = self._akshare()
            index_df = ak.stock_zh_index_spot_em()
            stock_df = ak.stock_zh_a_spot_em()
            sector_df = ak.stock_board_industry_name_em()
            if index_df.empty or stock_df.empty or sector_df.empty:
                raise ProviderFallbackError("AkShare 返回空数据")

            indices = self._build_indices(index_df)
            pct_changes = [_to_float(_pick(row, "涨跌幅")) for _idx, row in stock_df.iterrows()]
            up_count = sum(1 for value in pct_changes if value > 0)
            down_count = sum(1 for value in pct_changes if value < 0)
            turnover_cny = round(
                sum(_to_float(_pick(row, "成交额")) for _idx, row in stock_df.iterrows()) / 100_000_000,
                2,
            )
            raw_sectors = self._build_sectors(sector_df)
        except ProviderFallbackError:
            raise
        except Exception as exc:
            raise ProviderFallbackError(f"AkShare 请求失败: {exc.__class__.__name__}") from exc

        return MarketCloseSnapshot(
            trade_date=trade_date,
            indices=indices,
            breadth=MarketBreadth(
                up_count=up_count,
                down_count=down_count,
                limit_up_count=sum(1 for value in pct_changes if value >= 9.8),
                limit_down_count=sum(1 for value in pct_changes if value <= -9.8),
            ),
            turnover_cny=turnover_cny,
            market_state_tags=self._build_market_tags(up_count, down_count, turnover_cny),
            raw_sectors=raw_sectors,
        )

    def _build_indices(self, index_df: object) -> list[IndexSnapshot]:
        targets = {"上证指数", "创业板指"}
        indices: list[IndexSnapshot] = []
        for _idx, row in index_df.iterrows():
            name = str(_pick(row, "名称", "指数名称"))
            if name not in targets:
                continue
            indices.append(
                IndexSnapshot(
                    name=name,
                    code=str(_pick(row, "代码")),
                    close=_to_float(_pick(row, "最新价", "收盘")),
                    pct_change=_to_float(_pick(row, "涨跌幅")),
                )
            )
        if not indices:
            raise ProviderFallbackError("AkShare 未返回核心指数")
        return indices

    def _build_sectors(self, sector_df: object) -> list[RawSectorInput]:
        sectors: list[RawSectorInput] = []
        for _idx, row in sector_df.head(10).iterrows():
            up_count = _to_float(_pick(row, "上涨家数"))
            down_count = _to_float(_pick(row, "下跌家数"))
            total_count = up_count + down_count
            stock_up_ratio = round(up_count / total_count, 2) if total_count > 0 else 0.0
            pct_change = _to_float(_pick(row, "涨跌幅"))
            sectors.append(
                RawSectorInput(
                    name=str(_pick(row, "板块名称", "名称")),
                    pct_change=pct_change,
                    limit_up_count=0,
                    stock_up_ratio=stock_up_ratio,
                    turnover_change=0.0,
                    news_weight=min(max(abs(pct_change) / 8, 0.0), 1.0),
                )
            )
        if not sectors:
            raise ProviderFallbackError("AkShare 未返回板块数据")
        return sectors

    def _build_market_tags(self, up_count: int, down_count: int, turnover_cny: float) -> list[str]:
        tags: list[str] = []
        if up_count > down_count * 1.5:
            tags.append("普涨")
        elif down_count > up_count * 1.5:
            tags.append("普跌")
        else:
            tags.append("分化")
        tags.append("放量" if turnover_cny >= 10000 else "缩量")
        return tags


class FallbackMarketDataProvider:
    def __init__(
        self,
        primary: MarketDataProvider,
        fallback: MarketDataProvider,
        fallback_enabled: bool = True,
    ) -> None:
        self.primary = primary
        self.fallback = fallback
        self.fallback_enabled = fallback_enabled

    def get_close_snapshot(self, trade_date: str) -> MarketCloseSnapshot:
        snapshot, _status = self.get_close_snapshot_with_status(trade_date)
        return snapshot

    def get_close_snapshot_with_status(self, trade_date: str) -> tuple[MarketCloseSnapshot, ProviderStatus]:
        provider = _provider_name(self.primary, "market")
        try:
            snapshot = self.primary.get_close_snapshot(trade_date)
        except Exception as exc:
            reason = str(exc) or exc.__class__.__name__
            if not self.fallback_enabled:
                raise
            return self.fallback.get_close_snapshot(trade_date), ProviderStatus(
                provider=provider,
                status="fallback",
                fallback_used=True,
                reason=reason,
            )

        return snapshot, ProviderStatus(
            provider=provider,
            status="success",
            fallback_used=False,
            reason=None,
        )
