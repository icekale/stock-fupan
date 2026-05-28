from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo


CHINA_TZ = ZoneInfo("Asia/Shanghai")

CHINA_MARKET_HOLIDAYS_2026 = {
    "2026-01-01",
    "2026-01-02",
    "2026-02-16",
    "2026-02-17",
    "2026-02-18",
    "2026-02-19",
    "2026-02-20",
    "2026-02-23",
    "2026-04-06",
    "2026-05-01",
    "2026-05-04",
    "2026-05-05",
    "2026-06-19",
    "2026-09-25",
    "2026-10-01",
    "2026-10-02",
    "2026-10-05",
    "2026-10-06",
    "2026-10-07",
}


@dataclass(frozen=True)
class TradeDateValidation:
    is_valid: bool
    message: str = ""


def validate_trade_date(trade_date: str) -> TradeDateValidation:
    try:
        parsed = date.fromisoformat(trade_date)
    except ValueError:
        return TradeDateValidation(False, "交易日格式不正确，请使用 YYYY-MM-DD。")

    if parsed > _today_china():
        return TradeDateValidation(False, f"{trade_date} 是未来日期，不能提前生成复盘。")
    if parsed.weekday() >= 5:
        return TradeDateValidation(False, f"{trade_date} 是非交易日（周末），已停止生成。")
    if trade_date in CHINA_MARKET_HOLIDAYS_2026:
        return TradeDateValidation(False, f"{trade_date} 是 A 股休市日，已停止生成。")
    return TradeDateValidation(True)


def _today_china() -> date:
    return datetime.now(CHINA_TZ).date()
