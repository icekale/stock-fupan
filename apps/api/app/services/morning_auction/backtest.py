from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Sequence


def backtest_top_n(
    rows: Sequence[dict[str, object]],
    *,
    top_n: int,
    return_key: str = "open_to_close_return",
    round_trip_cost_bps: float = 0.0,
    skip_open_limit_up: bool = False,
) -> dict[str, object]:
    if top_n <= 0:
        raise ValueError("top_n must be positive")
    if round_trip_cost_bps < 0:
        raise ValueError("round_trip_cost_bps must be non-negative")

    by_date: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        by_date[str(row["trade_date"])].append(row)

    selected: list[dict[str, object]] = []
    skipped_open_limit_up_count = 0
    for day_rows in by_date.values():
        ranked = sorted(day_rows, key=lambda row: float(row.get("prob_3pct") or 0.0), reverse=True)
        day_selected = 0
        for row in ranked:
            if skip_open_limit_up and _is_open_limit_up(row):
                skipped_open_limit_up_count += 1
                continue
            selected.append(row)
            day_selected += 1
            if day_selected >= top_n:
                break

    cost = round_trip_cost_bps / 10_000
    returns = [float(row.get(return_key) or 0.0) - cost for row in selected]
    selected_count = len(selected)
    average_return = sum(returns) / selected_count if selected_count else 0.0
    hit_3pct_rate = _rate(returns, lambda value: value >= 0.03)
    hit_5pct_rate = _rate(returns, lambda value: value >= 0.05)
    win_rate = _rate(returns, lambda value: value > 0)
    loss_rate = _rate(returns, lambda value: value < 0)
    wins = [value for value in returns if value > 0]
    losses = [-value for value in returns if value < 0]
    avg_win = _average(wins)
    avg_loss = _average(losses)
    payoff_ratio = _ratio(avg_win, avg_loss)
    profit_factor = _ratio(sum(wins), sum(losses))
    breakeven_win_rate = None if payoff_ratio is None else 1 / (1 + payoff_ratio)
    expectancy = win_rate * avg_win - loss_rate * avg_loss

    return {
        "top_n": top_n,
        "return_key": return_key,
        "round_trip_cost_bps": round_trip_cost_bps,
        "skip_open_limit_up": skip_open_limit_up,
        "skipped_open_limit_up_count": skipped_open_limit_up_count,
        "trade_days": len(by_date),
        "selected_count": selected_count,
        "average_return": round(average_return, 6),
        "hit_3pct_rate": round(hit_3pct_rate, 6),
        "hit_5pct_rate": round(hit_5pct_rate, 6),
        "win_rate": round(win_rate, 6),
        "loss_rate": round(loss_rate, 6),
        "avg_win": round(avg_win, 6),
        "avg_loss": round(avg_loss, 6),
        "payoff_ratio": _round_optional(payoff_ratio),
        "profit_factor": _round_optional(profit_factor),
        "breakeven_win_rate": _round_optional(breakeven_win_rate),
        "expectancy": round(expectancy, 6),
    }


def _rate(values: list[float], predicate: Callable[[float], bool]) -> float:
    if not values:
        return 0.0
    return sum(1 for value in values if predicate(value)) / len(values)


def _average(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def _ratio(numerator: float, denominator: float) -> float | None:
    if denominator <= 0:
        return None
    return numerator / denominator


def _round_optional(value: float | None) -> float | None:
    if value is None:
        return None
    return round(value, 6)


def _is_open_limit_up(row: dict[str, object]) -> bool:
    open_price = _float_or_none(row.get("open_price"))
    prev_close_price = _float_or_none(row.get("prev_close_price"))
    if open_price is None or prev_close_price is None or prev_close_price <= 0:
        return False

    limit_pct = _limit_up_pct(str(row.get("symbol", "")))
    open_gap = open_price / prev_close_price - 1
    return open_gap >= limit_pct - 0.001


def _limit_up_pct(symbol: str) -> float:
    code = symbol.strip().upper().split(".", maxsplit=1)[0]
    if code.startswith(("300", "301", "688")):
        return 0.20
    return 0.10


def _float_or_none(value: object) -> float | None:
    if value is None:
        return None
    return float(value)
