from __future__ import annotations

from app.services.morning_auction.schemas import DailyBar, FilterResult


def evaluate_candidate_filters(
    *,
    symbol: str,
    name: str,
    listed_days: int,
    is_st: bool,
    is_suspended: bool,
    auction_return: float | None,
    auction_amount: float | None,
    daily_bars: list[DailyBar],
    require_auction_data: bool = False,
) -> FilterResult:
    risk_flags: list[str] = []
    if is_st or "ST" in name.upper():
        risk_flags.append("ST股票")
    if listed_days < 100:
        risk_flags.append("上市不足100天")
    if is_suspended:
        risk_flags.append("停牌")
    if require_auction_data and auction_return is None:
        risk_flags.append("竞价涨幅缺失")
    elif auction_return is not None and auction_return >= 8:
        risk_flags.append("竞价涨幅过高")
    if require_auction_data and auction_amount is None:
        risk_flags.append("竞价成交额缺失")
    elif auction_amount is not None and auction_amount < 5_000_000:
        risk_flags.append("竞价成交额不足")
    if not daily_bars:
        risk_flags.append("日K缺失")
    else:
        latest = daily_bars[-1]
        if latest.close <= 0 or latest.amount <= 0:
            risk_flags.append("日K成交异常")
    return FilterResult(passed=not risk_flags, risk_flags=risk_flags)
