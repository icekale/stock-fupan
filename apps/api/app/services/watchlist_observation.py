from app.providers.tickflow import WatchlistQuote
from app.schemas.report import SectorCandidate, WatchlistMatch, WatchlistObservation
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
    sector_matches = _sector_matches(matches, sectors)
    notes = [] if quotes else ["TickFlow 未返回自选股行情，已保留导入列表"]
    if not sector_matches:
        notes.append("暂未匹配到板块内自选股")
    return WatchlistObservation(
        import_id=import_id,
        total_count=len(items),
        quote_count=len(quotes),
        strongest=strongest,
        weakest=weakest,
        sector_matches=sector_matches,
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
