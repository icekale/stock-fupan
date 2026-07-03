from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Sequence


def backtest_top_n(rows: Sequence[dict[str, object]], *, top_n: int) -> dict[str, object]:
    by_date: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        by_date[str(row["trade_date"])].append(row)

    selected: list[dict[str, object]] = []
    for day_rows in by_date.values():
        ranked = sorted(day_rows, key=lambda row: float(row.get("prob_3pct") or 0.0), reverse=True)
        selected.extend(ranked[:top_n])

    returns = [float(row.get("open_to_close_return") or 0.0) for row in selected]
    selected_count = len(selected)
    average_return = sum(returns) / selected_count if selected_count else 0.0
    hit_3pct_rate = _rate(returns, lambda value: value >= 0.03)
    hit_5pct_rate = _rate(returns, lambda value: value >= 0.05)
    loss_rate = _rate(returns, lambda value: value < 0)

    return {
        "top_n": top_n,
        "trade_days": len(by_date),
        "selected_count": selected_count,
        "average_return": round(average_return, 6),
        "hit_3pct_rate": round(hit_3pct_rate, 6),
        "hit_5pct_rate": round(hit_5pct_rate, 6),
        "loss_rate": round(loss_rate, 6),
    }


def _rate(values: list[float], predicate: Callable[[float], bool]) -> float:
    if not values:
        return 0.0
    return sum(1 for value in values if predicate(value)) / len(values)
