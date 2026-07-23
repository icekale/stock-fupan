from __future__ import annotations

from app.services.morning_auction.schemas import DailyBar, FilterResult

_COMMON_A_SHARE_PREFIXES_BY_MARKET = {
    "SH": ("600", "601", "603", "605", "688"),
    "SZ": ("000", "001", "002", "003", "300", "301"),
}
_EXCLUDED_SECURITY_NAME_TOKENS = ("ETF", "LOF", "基金", "债", "REIT", "退")


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
    if not _is_common_a_share_symbol(symbol) or _is_excluded_security_name(name):
        risk_flags.append("非普通A股")
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


def _is_common_a_share_symbol(symbol: str) -> bool:
    code, market = _split_symbol(symbol)
    prefixes = _COMMON_A_SHARE_PREFIXES_BY_MARKET.get(market)
    return bool(prefixes and len(code) == 6 and code.startswith(prefixes))


def _split_symbol(symbol: str) -> tuple[str, str]:
    normalized = symbol.strip().upper()
    if "." in normalized:
        code, market = normalized.rsplit(".", maxsplit=1)
        return code, market
    return normalized, ""


def _is_excluded_security_name(name: str) -> bool:
    upper_name = name.upper()
    return upper_name.startswith(("C", "N")) or any(
        token in upper_name for token in _EXCLUDED_SECURITY_NAME_TOKENS
    )
