from __future__ import annotations

from app.services.morning_auction.data_sources import MorningAuctionDataSource
from app.services.morning_auction.features import build_feature_row
from app.services.morning_auction.filters import evaluate_candidate_filters
from app.services.morning_auction.schemas import AuctionSnapshot, MorningAuctionSample


def build_samples_for_trade_date(
    source: MorningAuctionDataSource,
    *,
    trade_date: str,
    lookback: int = 120,
) -> list[MorningAuctionSample]:
    samples: list[MorningAuctionSample] = []
    for candidate in source.candidate_universe(trade_date):
        symbol = str(candidate["symbol"])
        name = str(candidate.get("name", ""))
        bars = source.daily_bars(symbol, end_date=trade_date, lookback=lookback)
        if len(bars) < 2:
            continue

        current_bar = bars[-1]
        if current_bar.trade_date != trade_date:
            continue
        if (
            current_bar.open <= 0
            or current_bar.close <= 0
            or current_bar.volume <= 0
            or current_bar.amount <= 0
        ):
            continue

        prior_bars = bars[:-1]
        auction = source.auction_snapshot(symbol, trade_date=trade_date)
        auction_return = _auction_return(auction)
        auction_amount = _float_or_none(auction.auction_amount) if auction else None
        is_st = bool(candidate.get("is_st", False))
        filter_result = evaluate_candidate_filters(
            symbol=symbol,
            name=name,
            listed_days=int(candidate.get("listed_days", 9999)),
            is_st=is_st,
            is_suspended=bool(candidate.get("is_suspended", False)),
            auction_return=auction_return,
            auction_amount=auction_amount if auction_amount is not None else 10_000_000,
            daily_bars=prior_bars,
            require_auction_data=False,
        )
        if not filter_result.passed:
            continue

        features = build_feature_row(
            symbol=symbol,
            market_cap_float=_float_or_none(candidate.get("market_cap_float")),
            daily_bars=prior_bars,
            auction=auction,
            sector_strength=source.sector_strength(symbol, trade_date=trade_date),
            capital_strength=source.capital_strength(symbol, trade_date=trade_date),
        )
        next_bar = source.next_daily_bar(symbol, trade_date=trade_date)
        samples.append(
            MorningAuctionSample(
                trade_date=trade_date,
                symbol=symbol,
                name=name,
                features=features,
                prev_close_price=prior_bars[-1].close if prior_bars else None,
                open_price=current_bar.open,
                close_price=current_bar.close,
                next_open_price=next_bar.open if next_bar else None,
                next_close_price=next_bar.close if next_bar else None,
            )
        )
    return samples


def sample_to_row(sample: MorningAuctionSample) -> dict[str, object]:
    return {
        "trade_date": sample.trade_date,
        "symbol": sample.symbol,
        "name": sample.name,
        "features": sample.features,
        "prev_close_price": sample.prev_close_price,
        "open_price": sample.open_price,
        "close_price": sample.close_price,
        "next_open_price": sample.next_open_price,
        "next_close_price": sample.next_close_price,
        "open_to_close_return": sample.open_to_close_return,
        "t1_open_return": sample.t1_open_return,
        "t1_close_return": sample.t1_close_return,
        "main_label": sample.main_label,
        "strong_label": sample.strong_label,
        "safe_label": sample.safe_label,
        "risk_label": sample.risk_label,
        "t1_open_label": sample.t1_open_label,
        "t1_close_label": sample.t1_close_label,
        "t1_strong_label": sample.t1_strong_label,
        "t1_risk_label": sample.t1_risk_label,
    }


def _auction_return(auction: AuctionSnapshot | None) -> float | None:
    if auction is None or auction.indicative_price is None or auction.prev_close in (None, 0):
        return None
    return round((auction.indicative_price / auction.prev_close - 1) * 100, 4)


def _float_or_none(value: object) -> float | None:
    if value is None:
        return None
    return float(value)
