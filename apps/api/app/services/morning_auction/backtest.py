from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Sequence


def backtest_top_n(
    rows: Sequence[dict[str, object]],
    *,
    top_n: int,
    return_key: str = "open_to_close_return",
) -> dict[str, object]:
    if top_n <= 0:
        raise ValueError("top_n must be positive")

    by_date: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        by_date[str(row["trade_date"])].append(row)

    selected: list[dict[str, object]] = []
    for day_rows in by_date.values():
        ranked = sorted(day_rows, key=lambda row: float(row.get("prob_3pct") or 0.0), reverse=True)
        selected.extend(ranked[:top_n])

    returns = [float(row.get(return_key) or 0.0) for row in selected]
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
