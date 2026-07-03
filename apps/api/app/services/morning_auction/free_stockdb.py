from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime, timedelta
from typing import Any

import httpx

from app.services.morning_auction.schemas import AuctionSnapshot, DailyBar, MinuteBar


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
        self._prefetched_rows_by_date: dict[str, list[dict[str, object]]] | None = None
        self._prefetched_bars_by_code: dict[str, list[DailyBar]] | None = None
        self._client = FreeStockDbHttpClient(
            base_url=base_url,
            timeout_seconds=timeout_seconds,
            http_client=http_client,
        )

    def prefetch_daily_window(self, *, start_date: str | date, end_date: str | date, lookback: int) -> None:
        if lookback <= 0:
            raise ValueError("lookback must be positive")

        start_key = _start_key_for_lookback(_normalize_date_key(start_date), lookback)
        end_key = _end_key_for_label_lookahead(_normalize_date_key(end_date))
        if self._symbols is None:
            rows = self._client.vals(table="日k", k1="all:", k2=f"fwd:{start_key},{end_key}")
        else:
            rows = []
            for code in self._symbols:
                rows.extend(self._client.vals(table="日k", k1=f"key:{code}", k2=f"fwd:{start_key},{end_key}"))

        rows_by_date: dict[str, list[dict[str, object]]] = {}
        bars_by_code: dict[str, list[DailyBar]] = {}
        for row in rows:
            if not isinstance(row, dict) or "code" not in row or "date" not in row:
                continue
            date_key = str(row["date"])[:8]
            code = _raw_code(str(row["code"]))
            rows_by_date.setdefault(date_key, []).append(row)
            bars_by_code.setdefault(code, []).append(_daily_bar_from_row(row))

        for bars in bars_by_code.values():
            bars.sort(key=lambda bar: bar.trade_date)

        self._prefetched_rows_by_date = rows_by_date
        self._prefetched_bars_by_code = bars_by_code

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
        if self._prefetched_rows_by_date is not None:
            return list(self._prefetched_rows_by_date.get(date_key, []))

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
        cached = self._prefetched_bars_by_code.get(code) if self._prefetched_bars_by_code is not None else None
        if cached is not None:
            end_display = _display_date(end_key)
            bars = [bar for bar in cached if bar.trade_date <= end_display]
            return bars[-lookback:]

        rows = self._client.vals(table="日k", k1=f"key:{code}", k2=f"fwd:{start_key},{end_key}")
        bars = [_daily_bar_from_row(row) for row in rows if isinstance(row, dict)]
        bars.sort(key=lambda bar: bar.trade_date)
        return bars[-lookback:]

    def minute_bars(self, symbol: str, *, start_time: str | datetime, end_time: str | datetime) -> list[MinuteBar]:
        start_key = _normalize_datetime_key(start_time)
        end_key = _normalize_datetime_key(end_time)
        if end_key < start_key:
            raise ValueError("end_time must be on or after start_time")

        code = _raw_code(symbol)
        rows = self._client.vals(table="分钟k", k1=f"key:{code}", k2=f"fwd:{start_key},{end_key}")
        bars = [_minute_bar_from_row(row) for row in rows if isinstance(row, dict)]
        bars.sort(key=lambda bar: bar.trade_time)
        return bars

    def next_daily_bar(self, symbol: str, *, trade_date: str) -> DailyBar | None:
        date_key = _normalize_date_key(trade_date)
        code = _raw_code(symbol)
        cached = self._prefetched_bars_by_code.get(code) if self._prefetched_bars_by_code is not None else None
        if cached is not None:
            trade_display = _display_date(date_key)
            next_bars = [bar for bar in cached if bar.trade_date > trade_display]
            return next_bars[0] if next_bars else None

        start_key = (datetime.strptime(date_key, "%Y%m%d").date() + timedelta(days=1)).strftime("%Y%m%d")
        end_key = (datetime.strptime(date_key, "%Y%m%d").date() + timedelta(days=10)).strftime("%Y%m%d")
        rows = self._client.vals(table="日k", k1=f"key:{code}", k2=f"fwd:{start_key},{end_key}")
        bars = [_daily_bar_from_row(row) for row in rows if isinstance(row, dict)]
        bars.sort(key=lambda bar: bar.trade_date)
        return bars[0] if bars else None

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


def _minute_bar_from_row(row: dict[str, object]) -> MinuteBar:
    return MinuteBar(
        trade_time=_display_datetime(row["date"]),
        open=float(row["open"]),
        high=float(row["high"]),
        low=float(row["low"]),
        close=float(row["close"]),
        volume=float(row["volume"]),
        amount=float(row["amount"]),
    )


def _normalize_date_key(value: str | date) -> str:
    if isinstance(value, date):
        return value.strftime("%Y%m%d")
    text = str(value).strip()
    if len(text) == 8 and text.isdigit():
        return text
    if len(text) == 10:
        return date.fromisoformat(text).strftime("%Y%m%d")
    raise ValueError("date must be YYYY-MM-DD or YYYYMMDD")


def _normalize_datetime_key(value: str | datetime) -> str:
    if isinstance(value, datetime):
        return value.strftime("%Y%m%d%H%M%S")
    text = str(value).strip()
    if len(text) == 14 and text.isdigit():
        return text
    normalized = text.replace("T", " ")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(normalized, fmt).strftime("%Y%m%d%H%M%S")
        except ValueError:
            pass
    raise ValueError("datetime must be YYYY-MM-DD HH:MM[:SS] or YYYYMMDDHHMMSS")


def _display_date(value: object) -> str:
    text = str(value)[:8]
    parsed = datetime.strptime(text, "%Y%m%d").date()
    return parsed.isoformat()


def _display_datetime(value: object) -> str:
    text = str(value)[:14]
    parsed = datetime.strptime(text, "%Y%m%d%H%M%S")
    return parsed.strftime("%Y-%m-%d %H:%M:%S")


def _start_key_for_lookback(end_key: str, lookback: int) -> str:
    end = datetime.strptime(end_key, "%Y%m%d").date()
    calendar_days = max(lookback * 3 + 10, lookback + 10)
    return (end - timedelta(days=calendar_days)).strftime("%Y%m%d")


def _end_key_for_label_lookahead(end_key: str) -> str:
    end = datetime.strptime(end_key, "%Y%m%d").date()
    return (end + timedelta(days=10)).strftime("%Y%m%d")


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
