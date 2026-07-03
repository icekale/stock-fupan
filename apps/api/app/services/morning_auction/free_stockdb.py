from __future__ import annotations

from datetime import date, datetime, timedelta
from collections.abc import Sequence
from typing import Any

import httpx

from app.services.morning_auction.schemas import AuctionSnapshot, DailyBar


class FreeStockDbError(RuntimeError):
    """Raised when the free-stockdb HTTP service returns an unusable response."""


class FreeStockDbHttpClient:
    def __init__(
        self,
        *,
        base_url: str,
        timeout_seconds: float = 10.0,
        http_client: httpx.Client | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/") + "/"
        self._timeout_seconds = timeout_seconds
        self._client = http_client or httpx.Client(timeout=timeout_seconds)

    def vals(self, *, table: str, k1: str, k2: str) -> list[Any]:
        return self._request_list({"cmd": "vals", "t": table, "k1": k1, "k2": k2})

    def keys(self, *, table: str, k1: str | None = None, k2: str | None = None) -> list[Any]:
        params = {"cmd": "keys", "t": table}
        if k1 is not None:
            params["k1"] = k1
        if k2 is not None:
            params["k2"] = k2
        return self._request_list(params)

    def _request_list(self, params: dict[str, str]) -> list[Any]:
        try:
            response = self._client.get(self._base_url, params=params, timeout=self._timeout_seconds)
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPError as exc:
            raise FreeStockDbError(f"free-stockdb request failed: {exc}") from exc
        except ValueError as exc:
            raise FreeStockDbError("free-stockdb returned invalid JSON") from exc

        if not isinstance(payload, list):
            raise FreeStockDbError("free-stockdb expected list payload")
        return payload


class FreeStockDbMorningAuctionDataSource:
    def __init__(
        self,
        *,
        base_url: str,
        symbols: Sequence[str] | None = None,
        timeout_seconds: float = 10.0,
        http_client: httpx.Client | None = None,
    ) -> None:
        self._symbols = [_raw_code(symbol) for symbol in symbols] if symbols is not None else None
        self._client = FreeStockDbHttpClient(
            base_url=base_url,
            timeout_seconds=timeout_seconds,
            http_client=http_client,
        )

    def candidate_universe(self, trade_date: str) -> list[dict[str, object]]:
        date_key = _normalize_date_key(trade_date)
        rows = self._candidate_rows(date_key)
        candidates: list[dict[str, object]] = []
        for row in rows:
            if not isinstance(row, dict) or "code" not in row:
                continue
            candidates.append(
                {
                    "symbol": _symbol_with_suffix(str(row["code"])),
                    "name": str(row.get("name", "")),
                    "is_st": bool(row.get("is_st", False)),
                    "is_suspended": False,
                    "listed_days": 9999,
                    "market_cap_float": _float_or_none(row.get("float_mv")),
                }
            )
        return candidates

    def _candidate_rows(self, date_key: str) -> list[Any]:
        if self._symbols is None:
            return self._client.vals(table="日k", k1="all:", k2=f"key:{date_key}")

        rows: list[Any] = []
        for code in self._symbols:
            rows.extend(self._client.vals(table="日k", k1=f"key:{code}", k2=f"key:{date_key}"))
        return rows

    def daily_bars(self, symbol: str, *, end_date: str, lookback: int) -> list[DailyBar]:
        if lookback <= 0:
            raise ValueError("lookback must be positive")

        end_key = _normalize_date_key(end_date)
        start_key = _start_key_for_lookback(end_key, lookback)
        code = _raw_code(symbol)
        rows = self._client.vals(table="日k", k1=f"key:{code}", k2=f"fwd:{start_key},{end_key}")
        bars = [_daily_bar_from_row(row) for row in rows if isinstance(row, dict)]
        bars.sort(key=lambda bar: bar.trade_date)
        return bars[-lookback:]

    def auction_snapshot(self, symbol: str, *, trade_date: str) -> AuctionSnapshot | None:
        return None

    def sector_strength(self, symbol: str, *, trade_date: str) -> float | None:
        return None

    def capital_strength(self, symbol: str, *, trade_date: str) -> float | None:
        return None


def _daily_bar_from_row(row: dict[str, object]) -> DailyBar:
    return DailyBar(
        trade_date=_display_date(row["date"]),
        open=float(row["open"]),
        high=float(row["high"]),
        low=float(row["low"]),
        close=float(row["close"]),
        volume=float(row["volume"]),
        amount=float(row["amount"]),
        turnover_rate=_float_or_none(row.get("turnover")),
    )


def _normalize_date_key(value: str) -> str:
    text = str(value).strip()
    if len(text) == 8 and text.isdigit():
        return text
    if len(text) == 10:
        return date.fromisoformat(text).strftime("%Y%m%d")
    raise ValueError("date must be YYYY-MM-DD or YYYYMMDD")


def _display_date(value: object) -> str:
    text = str(value)[:8]
    parsed = datetime.strptime(text, "%Y%m%d").date()
    return parsed.isoformat()


def _start_key_for_lookback(end_key: str, lookback: int) -> str:
    end = datetime.strptime(end_key, "%Y%m%d").date()
    calendar_days = max(lookback * 3 + 10, lookback + 10)
    return (end - timedelta(days=calendar_days)).strftime("%Y%m%d")


def _raw_code(symbol: str) -> str:
    text = str(symbol).strip().upper()
    if "." in text:
        text = text.split(".", 1)[0]
    if len(text) > 6 and text[:2] in {"SH", "SZ", "BJ"}:
        text = text[2:]
    return text


def _symbol_with_suffix(code: str) -> str:
    raw = _raw_code(code)
    if raw.startswith(("920", "8", "4")):
        suffix = "BJ"
    elif raw.startswith(("6", "9")):
        suffix = "SH"
    else:
        suffix = "SZ"
    return f"{raw}.{suffix}"


def _float_or_none(value: object) -> float | None:
    if value is None:
        return None
    return float(value)
