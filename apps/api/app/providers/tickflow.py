from typing import Any, Protocol

import httpx
from pydantic import BaseModel

from app.providers.market import ProviderFallbackError, ProviderStatus


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
