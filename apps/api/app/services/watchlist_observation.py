from app.providers.quotes import WatchlistQuote
from app.schemas.report import SectorCandidate, WatchlistMatch, WatchlistObservation, WatchlistRiskItem
from app.watchlist.parser import WatchlistItem


def build_watchlist_observation(
    import_id: int | None,
    items: list[WatchlistItem],
    quotes: list[WatchlistQuote],
    sectors: list[SectorCandidate],
) -> WatchlistObservation:
    if not items:
        return WatchlistObservation(
            import_id=import_id,
            total_count=0,
            quote_count=0,
            notes=["未导入自选股"],
        )

    quote_by_symbol = {quote.symbol: quote for quote in quotes}
    matches = [_match_from_item(item, quote_by_symbol.get(item.symbol)) for item in items]
    quoted_matches = [match for match in matches if match.pct_change is not None]
    strongest = sorted(quoted_matches, key=lambda match: match.pct_change or 0, reverse=True)[:5]
    weakest = sorted(quoted_matches, key=lambda match: match.pct_change or 0)[:5]
    risk_items = _daily_risk_items(matches, quote_by_symbol)
    sector_matches = _sector_matches(matches, sectors)
    notes = [] if quotes else ["行情源未返回自选股行情，已保留导入列表"]
    if not sector_matches:
        notes.append("暂未匹配到板块内自选股")
    if quotes and not risk_items:
        notes.append("自选股当日未触发显著风险信号")
    return WatchlistObservation(
        import_id=import_id,
        total_count=len(items),
        quote_count=len(quotes),
        strongest=strongest,
        weakest=weakest,
        sector_matches=sector_matches,
        risk_items=risk_items,
        notes=notes,
    )


def _match_from_item(item: WatchlistItem, quote: WatchlistQuote | None) -> WatchlistMatch:
    name = quote.name if quote and quote.name else item.name
    pct_change = quote.pct_change if quote else None
    reason = "自选股涨跌幅居前" if pct_change is not None and pct_change >= 0 else "自选股风险观察"
    if pct_change is None:
        reason = "已导入自选股，等待行情确认"
    return WatchlistMatch(symbol=item.symbol, name=name, pct_change=pct_change, reason=reason)


def _sector_matches(
    matches: list[WatchlistMatch],
    sectors: list[SectorCandidate],
) -> list[WatchlistMatch]:
    results: list[WatchlistMatch] = []
    for match in matches:
        for sector in sectors:
            if match.name and match.name in sector.name:
                results.append(
                    match.model_copy(
                        update={"sector": sector.name, "reason": f"名称命中{sector.name}方向"}
                    )
                )
                break
    return results[:10]


def _daily_risk_items(
    matches: list[WatchlistMatch],
    quote_by_symbol: dict[str, WatchlistQuote],
) -> list[WatchlistRiskItem]:
    risks = [
        risk
        for match in matches
        if (risk := _risk_item(match, quote_by_symbol.get(match.symbol))) is not None
    ]
    level_rank = {"high": 0, "medium": 1, "low": 2}
    return sorted(
        risks,
        key=lambda item: (
            level_rank.get(item.risk_level, 9),
            item.pct_change if item.pct_change is not None else 999,
        ),
    )[:10]


def _risk_item(match: WatchlistMatch, quote: WatchlistQuote | None) -> WatchlistRiskItem | None:
    if quote is None:
        return None

    reasons: list[str] = []
    risk_level = "low"
    pct_change = match.pct_change

    if pct_change is not None:
        if pct_change <= -5:
            reasons.append("日内跌幅达到5%以上")
            risk_level = "high"
        elif pct_change <= -3:
            reasons.append("日内跌幅达到3%以上")
            risk_level = "medium"

    if quote.turnover_rate is not None and quote.turnover_rate >= 20 and pct_change is not None and pct_change < 0:
        reasons.append("高换手下跌")
        if risk_level == "low":
            risk_level = "medium"

    if quote.capital_strength and _looks_like_capital_outflow(quote.capital_strength):
        reasons.append(quote.capital_strength)
        if risk_level == "low":
            risk_level = "medium"

    if not reasons:
        return None

    return WatchlistRiskItem(
        symbol=match.symbol,
        name=match.name,
        pct_change=pct_change,
        risk_level=risk_level,
        risk_reasons=reasons,
    )


def _looks_like_capital_outflow(value: str) -> bool:
    return any(keyword in value for keyword in ("净流出", "流出", "弱", "撤退"))
