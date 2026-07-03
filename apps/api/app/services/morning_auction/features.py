from __future__ import annotations

from app.services.morning_auction.schemas import AuctionSnapshot, DailyBar

FEATURE_VERSION = "morning_auction_features_v1"


def build_feature_row(
    *,
    symbol: str,
    market_cap_float: float | None,
    daily_bars: list[DailyBar],
    auction: AuctionSnapshot | None,
    sector_strength: float | None,
    capital_strength: float | None,
) -> dict[str, float | int | None]:
    latest = daily_bars[-1] if daily_bars else None
    previous = daily_bars[-2] if len(daily_bars) >= 2 else None
    close_values = [bar.close for bar in daily_bars]
    volume_values = [bar.volume for bar in daily_bars]
    amount_values = [bar.amount for bar in daily_bars]

    row: dict[str, float | int | None] = {
        "market_cap_float": _round_or_none(market_cap_float),
        "prev_return": _pct_change(latest.close, previous.open) if latest and previous else None,
        "prev_turnover": latest.turnover_rate if latest else None,
        "return_3d": _window_return(close_values, 3),
        "return_5d": _window_return(close_values, 5),
        "volume_ratio_3d": _last_vs_average(volume_values, 3),
        "amount_ratio_3d": _last_vs_average(amount_values, 3),
        "close_vs_ma5": _close_vs_ma(close_values, 5),
        "close_vs_ma10": _close_vs_ma(close_values, 10),
        "close_vs_ma20": _close_vs_ma(close_values, 20),
        "new_high_60d": _new_high(close_values, 60),
        "sector_strength": _round_or_none(sector_strength),
        "capital_strength": _round_or_none(capital_strength),
    }
    row.update(_auction_features(auction, latest))
    row["risk_score"] = _risk_score(row)
    return row


def _auction_features(
    auction: AuctionSnapshot | None,
    latest: DailyBar | None,
) -> dict[str, float | int | None]:
    if auction is None:
        return {
            "auction_data_available": 0,
            "auction_return": None,
            "auction_volume_ratio": None,
            "auction_amount_ratio": None,
            "bid_ask_imbalance": None,
            "unmatched_buy_ratio": None,
        }

    prev_close = auction.prev_close or (latest.close if latest else None)
    return {
        "auction_data_available": 1,
        "auction_return": _pct_change(auction.indicative_price, prev_close),
        "auction_volume_ratio": _ratio(auction.auction_volume, latest.volume if latest else None),
        "auction_amount_ratio": _ratio(auction.auction_amount, latest.amount if latest else None),
        "bid_ask_imbalance": _imbalance(auction.bid_volume, auction.ask_volume),
        "unmatched_buy_ratio": _ratio(auction.unmatched_volume, auction.auction_volume),
    }


def _pct_change(value: float | None, base: float | None) -> float | None:
    if value is None or base is None or base == 0:
        return None
    return round((value / base - 1) * 100, 4)


def _ratio(value: float | None, base: float | None) -> float | None:
    if value is None or base is None or base == 0:
        return None
    return round(value / base, 6)


def _imbalance(bid: float | None, ask: float | None) -> float | None:
    if bid is None or ask is None or bid + ask == 0:
        return None
    return round((bid - ask) / (bid + ask), 6)


def _window_return(values: list[float], window: int) -> float | None:
    if len(values) < window or values[-window] == 0:
        return None
    return round((values[-1] / values[-window] - 1) * 100, 4)


def _last_vs_average(values: list[float], window: int) -> float | None:
    if len(values) < window:
        return None

    base_values = values[-window:-1]
    if not base_values:
        return None
    average = sum(base_values) / len(base_values)
    if average == 0:
        return None
    return round(values[-1] / average, 6)


def _close_vs_ma(values: list[float], window: int) -> float | None:
    if len(values) < window:
        return 0.0

    average = sum(values[-window:]) / window
    if average == 0:
        return None
    return round((values[-1] / average - 1) * 100, 4)


def _new_high(values: list[float], window: int) -> int:
    if not values:
        return 0
    recent = values[-window:]
    return int(values[-1] >= max(recent))


def _risk_score(row: dict[str, float | int | None]) -> float:
    score = 0.0
    auction_return = row.get("auction_return")
    if isinstance(auction_return, int | float) and auction_return >= 7:
        score += 20

    prev_return = row.get("prev_return")
    if isinstance(prev_return, int | float) and prev_return <= -3:
        score += 10

    return score


def _round_or_none(value: float | None) -> float | None:
    return None if value is None else round(float(value), 6)
