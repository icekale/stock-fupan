from typing import Any, Protocol

import httpx
from pydantic import BaseModel

from app.providers.market import MarketBreadth, MarketCloseSnapshot, ProviderFallbackError, ProviderStatus
from app.rules.scoring import RawSectorInput
from app.schemas.report import IndexSnapshot


DEFAULT_MARKET_SYMBOLS = ["600000.SH", "000001.SZ", "300750.SZ", "002594.SZ", "601318.SH"]
INDEX_SYMBOLS = ["000001.SH", "399006.SZ"]


class WatchlistQuote(BaseModel):
    symbol: str
    name: str | None = None
    last_price: float | None = None
    pct_change: float | None = None
    turnover_cny: float | None = None
    volume: float | None = None
    quote_time: str | None = None


class TickFlowQuoteProvider(Protocol):
    def get_quotes(self, symbols: list[str]) -> list[WatchlistQuote]:
        raise NotImplementedError


class FakeTickFlowProvider:
    provider_name = "fake_tickflow"

    def get_quotes(self, symbols: list[str]) -> list[WatchlistQuote]:
        fake_names = {"600000.SH": "浦发银行", "000001.SZ": "平安银行", "300750.SZ": "宁德时代"}
        return [
            WatchlistQuote(
                symbol=symbol,
                name=fake_names.get(symbol),
                last_price=10.0 + index,
                pct_change=2.5 - index,
                turnover_cny=100000000 + index * 1000000,
                volume=10000 + index,
                quote_time="2026-05-26T15:00:00+08:00",
            )
            for index, symbol in enumerate(symbols)
        ]


class TickFlowProvider:
    provider_name = "tickflow"

    def __init__(
        self,
        api_key: str,
        base_url: str,
        timeout_seconds: float = 12,
        http_client: object | None = None,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self._owns_client = http_client is None
        self.http_client = http_client or httpx.Client()

    def close(self) -> None:
        if self._owns_client:
            self.http_client.close()

    def get_quotes(self, symbols: list[str]) -> list[WatchlistQuote]:
        if not symbols:
            return []
        if not self.api_key:
            raise ProviderFallbackError("TICKFLOW_API_KEY 未配置")
        try:
            response = self.http_client.post(
                f"{self.base_url}/v1/quotes",
                headers={"x-api-key": self.api_key},
                json={"symbols": symbols},
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
        except httpx.TimeoutException as exc:
            raise ProviderFallbackError("TickFlow 请求超时") from exc
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code if exc.response is not None else None
            raise ProviderFallbackError(_safe_status_error(status_code)) from exc
        except Exception as exc:
            raise ProviderFallbackError(f"TickFlow 请求失败: {exc.__class__.__name__}") from exc
        return [_quote_from_item(item) for item in _extract_items(payload)]


class TickFlowMarketDataProvider:
    provider_name = "tickflow"

    def __init__(
        self,
        api_key: str,
        base_url: str,
        symbols: list[str] | None = None,
        timeout_seconds: float = 12,
        http_client: object | None = None,
    ) -> None:
        self.quote_provider = TickFlowProvider(
            api_key=api_key,
            base_url=base_url,
            timeout_seconds=timeout_seconds,
            http_client=http_client,
        )
        self.symbols = symbols or DEFAULT_MARKET_SYMBOLS

    def close(self) -> None:
        self.quote_provider.close()

    def get_close_snapshot(self, trade_date: str) -> MarketCloseSnapshot:
        quotes = self.quote_provider.get_quotes([*INDEX_SYMBOLS, *self.symbols])
        indices = _indices_from_quotes(quotes)
        equity_quotes = [quote for quote in quotes if quote.symbol not in set(INDEX_SYMBOLS)]
        quoted_changes = [quote.pct_change for quote in equity_quotes if quote.pct_change is not None]
        if not indices or not quoted_changes:
            raise ProviderFallbackError("TickFlow 行情数据不足")
        turnover_cny = round(
            sum(quote.turnover_cny or 0 for quote in equity_quotes) / 100_000_000,
            2,
        )
        raw_sectors = _sectors_from_quotes(equity_quotes)
        if not raw_sectors:
            raise ProviderFallbackError("TickFlow 未返回可排序标的")
        return MarketCloseSnapshot(
            trade_date=trade_date,
            indices=indices,
            breadth=MarketBreadth(
                up_count=sum(1 for change in quoted_changes if change > 0),
                down_count=sum(1 for change in quoted_changes if change < 0),
                limit_up_count=sum(1 for change in quoted_changes if change >= 9.8),
                limit_down_count=sum(1 for change in quoted_changes if change <= -9.8),
            ),
            turnover_cny=turnover_cny,
            market_state_tags=_market_tags(quoted_changes, turnover_cny),
            raw_sectors=raw_sectors,
        )


class FallbackTickFlowProvider:
    def __init__(
        self,
        primary: TickFlowQuoteProvider,
        fallback: TickFlowQuoteProvider,
        fallback_enabled: bool = True,
    ) -> None:
        self.primary = primary
        self.fallback = fallback
        self.fallback_enabled = fallback_enabled

    def get_quotes(self, symbols: list[str]) -> list[WatchlistQuote]:
        quotes, _status = self.get_quotes_with_status(symbols)
        return quotes

    def get_quotes_with_status(self, symbols: list[str]) -> tuple[list[WatchlistQuote], ProviderStatus]:
        try:
            quotes = self.primary.get_quotes(symbols)
        except Exception as exc:
            reason = str(exc) or exc.__class__.__name__
            if not self.fallback_enabled:
                raise
            return self.fallback.get_quotes(symbols), ProviderStatus(
                provider="tickflow",
                status="fallback",
                fallback_used=True,
                reason=reason,
            )
        return quotes, ProviderStatus(
            provider="tickflow",
            status="success",
            fallback_used=False,
            reason=None,
        )


def _extract_items(payload: object) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        data = payload.get("data") or payload.get("items") or payload.get("results")
    else:
        data = payload
    if not isinstance(data, list):
        raise ProviderFallbackError("TickFlow 响应结构异常")
    return [item for item in data if isinstance(item, dict)]


def _quote_from_item(item: dict[str, Any]) -> WatchlistQuote:
    symbol = str(item.get("symbol") or item.get("ticker") or item.get("code") or "")
    if not symbol:
        raise ProviderFallbackError("TickFlow 响应缺少 symbol")
    ext = item.get("ext")
    ext_item = ext if isinstance(ext, dict) else {}
    change_pct = (
        item.get("pct_change")
        or item.get("change_percent")
        or item.get("percent")
        or ext_item.get("change_pct")
    )
    pct_change = _optional_float(change_pct)
    if pct_change is not None and abs(pct_change) <= 1:
        pct_change = pct_change * 100
    return WatchlistQuote(
        symbol=symbol,
        name=_optional_str(item.get("name") or ext_item.get("name")),
        last_price=_optional_float(item.get("last_price") or item.get("price") or item.get("last")),
        pct_change=pct_change,
        turnover_cny=_optional_float(item.get("turnover_cny") or item.get("turnover") or item.get("amount")),
        volume=_optional_float(item.get("volume")),
        quote_time=_optional_str(item.get("quote_time") or item.get("time") or item.get("timestamp")),
    )


def _indices_from_quotes(quotes: list[WatchlistQuote]) -> list[IndexSnapshot]:
    index_names = {"000001.SH": "上证指数", "399006.SZ": "创业板指"}
    results: list[IndexSnapshot] = []
    for quote in quotes:
        if quote.symbol not in index_names or quote.last_price is None or quote.pct_change is None:
            continue
        results.append(
            IndexSnapshot(
                name=quote.name or index_names[quote.symbol],
                code=quote.symbol.split(".")[0],
                close=quote.last_price,
                pct_change=quote.pct_change,
            )
        )
    return results


def _sectors_from_quotes(quotes: list[WatchlistQuote]) -> list[RawSectorInput]:
    ranked = sorted(
        [quote for quote in quotes if quote.pct_change is not None],
        key=lambda quote: quote.pct_change or 0,
        reverse=True,
    )
    return [
        RawSectorInput(
            name=quote.name or quote.symbol,
            pct_change=quote.pct_change or 0,
            limit_up_count=1 if (quote.pct_change or 0) >= 9.8 else 0,
            stock_up_ratio=1.0 if (quote.pct_change or 0) > 0 else 0.0,
            turnover_change=0.0,
            news_weight=min(max(abs(quote.pct_change or 0) / 8, 0.0), 1.0),
        )
        for quote in ranked[:10]
    ]


def _market_tags(changes: list[float], turnover_cny: float) -> list[str]:
    up_count = sum(1 for change in changes if change > 0)
    down_count = sum(1 for change in changes if change < 0)
    if up_count > down_count * 1.5:
        breadth = "普涨"
    elif down_count > up_count * 1.5:
        breadth = "普跌"
    else:
        breadth = "分化"
    return [breadth, "放量" if turnover_cny >= 10000 else "缩量"]


def _optional_str(value: object) -> str | None:
    return str(value) if value is not None and str(value) else None


def _optional_float(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_status_error(status_code: object) -> str:
    return "TickFlow HTTP 请求失败" if status_code is None else f"TickFlow HTTP {status_code}"
