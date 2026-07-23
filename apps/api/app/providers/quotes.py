from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel

from app.providers.market import ProviderFallbackError, ProviderStatus


class WatchlistQuote(BaseModel):
    symbol: str
    name: str | None = None
    last_price: float | None = None
    pct_change: float | None = None
    turnover_cny: float | None = None
    turnover_rate: float | None = None
    capital_strength: str | None = None
    volume: float | None = None
    quote_time: str | None = None


class QuoteProvider(Protocol):
    provider_name: str

    def get_quotes(self, symbols: list[str]) -> list[WatchlistQuote]:
        raise NotImplementedError


class FakeQuoteProvider:
    provider_name = "fake_quote"

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


class FallbackQuoteProvider:
    def __init__(
        self,
        primary: QuoteProvider,
        fallback: QuoteProvider,
        fallback_enabled: bool = True,
    ) -> None:
        self.primary = primary
        self.fallback = fallback
        self.fallback_enabled = fallback_enabled
        self.provider_name = getattr(primary, "provider_name", "quote")

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
                provider=self.provider_name,
                status="fallback",
                fallback_used=True,
                reason=reason,
            )
        return quotes, ProviderStatus(
            provider=self.provider_name,
            status="success",
            fallback_used=False,
            reason=None,
        )

    def close(self) -> None:
        for provider in (self.primary, self.fallback):
            close = getattr(provider, "close", None)
            if callable(close):
                close()


def provider_error(message: str) -> ProviderFallbackError:
    return ProviderFallbackError(message)
