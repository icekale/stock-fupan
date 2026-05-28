from datetime import date

from app.services import trading_calendar
from app.services.trading_calendar import validate_trade_date


def test_validate_trade_date_accepts_current_trading_day(monkeypatch) -> None:
    monkeypatch.setattr(trading_calendar, "_today_china", lambda: date(2026, 5, 28))

    result = validate_trade_date("2026-05-28")

    assert result.is_valid is True


def test_validate_trade_date_rejects_future_date(monkeypatch) -> None:
    monkeypatch.setattr(trading_calendar, "_today_china", lambda: date(2026, 5, 28))

    result = validate_trade_date("2026-05-29")

    assert result.is_valid is False
    assert "未来日期" in result.message


def test_validate_trade_date_rejects_weekend(monkeypatch) -> None:
    monkeypatch.setattr(trading_calendar, "_today_china", lambda: date(2026, 5, 30))

    result = validate_trade_date("2026-05-30")

    assert result.is_valid is False
    assert "非交易日" in result.message


def test_validate_trade_date_rejects_market_holiday(monkeypatch) -> None:
    monkeypatch.setattr(trading_calendar, "_today_china", lambda: date(2026, 10, 1))

    result = validate_trade_date("2026-10-01")

    assert result.is_valid is False
    assert "休市日" in result.message


def test_validate_trade_date_rejects_bad_format() -> None:
    result = validate_trade_date("2026/05/28")

    assert result.is_valid is False
    assert "YYYY-MM-DD" in result.message
