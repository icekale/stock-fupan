from __future__ import annotations

from collections.abc import Sequence
from datetime import date, timedelta
from pathlib import Path
from typing import Protocol

from app.services.morning_auction.artifacts import ensure_parent, read_json
from app.services.morning_auction.features import build_feature_row
from app.services.morning_auction.filters import evaluate_candidate_filters
from app.services.morning_auction.predictor import build_run, bucket_prediction
from app.services.morning_auction.schemas import (
    AuctionSnapshot,
    DailyBar,
    MorningAuctionBucket,
    MorningAuctionPredictionItem,
    MorningAuctionRun,
    MorningAuctionTrialEntry,
    MorningAuctionTrialLog,
)
from app.services.morning_auction.scorer import score_rows_with_model

GUARD_RULE = "10:00收益<0则退出，否则持有到T+1收盘"


class LivePredictionSource(Protocol):
    def candidate_universe(self, trade_date: str) -> list[dict[str, object]]: ...

    def daily_bars(self, symbol: str, *, end_date: str, lookback: int) -> list[DailyBar]: ...

    def auction_snapshot(self, symbol: str, *, trade_date: str) -> AuctionSnapshot | None: ...

    def sector_strength(self, symbol: str, *, trade_date: str) -> float | None: ...

    def capital_strength(self, symbol: str, *, trade_date: str) -> float | None: ...


def build_live_prediction_rows(
    source: LivePredictionSource,
    *,
    trade_date: str,
    lookback: int,
    max_calendar_backtrack: int = 14,
) -> tuple[list[dict[str, object]], str]:
    feature_end_date, candidates = _previous_candidate_universe(
        source,
        trade_date=trade_date,
        max_calendar_backtrack=max_calendar_backtrack,
    )
    _prefetch_daily_window_if_available(source, feature_end_date=feature_end_date, lookback=lookback)

    rows: list[dict[str, object]] = []
    for candidate in candidates:
        symbol = str(candidate["symbol"])
        name = str(candidate.get("name", ""))
        bars = source.daily_bars(symbol, end_date=feature_end_date, lookback=lookback)
        if len(bars) < 2:
            continue
        if any(bar.close <= 0 or bar.volume <= 0 or bar.amount <= 0 for bar in bars[-2:]):
            continue

        auction = source.auction_snapshot(symbol, trade_date=trade_date)
        auction_return = _auction_return(auction)
        auction_amount = _float_or_none(auction.auction_amount) if auction else None
        filter_result = evaluate_candidate_filters(
            symbol=symbol,
            name=name,
            listed_days=int(candidate.get("listed_days", 9999)),
            is_st=bool(candidate.get("is_st", False)),
            is_suspended=bool(candidate.get("is_suspended", False)),
            auction_return=auction_return,
            auction_amount=auction_amount if auction_amount is not None else 10_000_000,
            daily_bars=bars,
            require_auction_data=False,
        )
        if not filter_result.passed:
            continue

        features = build_feature_row(
            symbol=symbol,
            market_cap_float=_float_or_none(candidate.get("market_cap_float")),
            daily_bars=bars,
            auction=auction,
            sector_strength=source.sector_strength(symbol, trade_date=trade_date),
            capital_strength=source.capital_strength(symbol, trade_date=trade_date),
        )
        rows.append(
            {
                "trade_date": trade_date,
                "feature_end_date": feature_end_date,
                "symbol": symbol,
                "name": name,
                "features": features,
                "prev_close_price": bars[-1].close,
                "open_price": None,
                "close_price": None,
                "risk_flags": filter_result.risk_flags,
                "data_quality": _data_quality_flags(auction),
            }
        )
    return rows, feature_end_date


def prediction_items_from_scored_rows(
    rows: Sequence[dict[str, object]],
    *,
    top_n: int,
    max_items: int,
) -> list[MorningAuctionPredictionItem]:
    ranked = sorted(rows, key=lambda row: float(row.get("prob_3pct") or 0.0), reverse=True)
    items: list[MorningAuctionPredictionItem] = []
    for rank, row in enumerate(ranked[:max_items], start=1):
        prob_3pct = float(row.get("prob_3pct") or 0.0)
        strong_5pct_score = float(row.get("prob_5pct") or prob_3pct)
        risk_flags = [str(flag) for flag in row.get("risk_flags", [])]
        if rank <= top_n and not risk_flags:
            bucket = MorningAuctionBucket.SELECTED
        else:
            bucket = bucket_prediction(
                prob_3pct=prob_3pct,
                strong_5pct_score=strong_5pct_score,
                risk_flags=risk_flags,
            )
            if bucket == MorningAuctionBucket.SELECTED:
                bucket = MorningAuctionBucket.ATTACK
        items.append(
            MorningAuctionPredictionItem(
                symbol=str(row.get("symbol", "")),
                name=str(row.get("name", "")),
                prob_3pct=prob_3pct,
                strong_5pct_score=strong_5pct_score,
                bucket=bucket,
                rank=rank,
                prev_close_price=_float_or_none(row.get("prev_close_price")),
                feature_end_date=str(row.get("feature_end_date") or ""),
                guard_rule=GUARD_RULE if rank <= top_n else None,
                strategy_note="Top3试运行候选" if rank <= top_n else "候选观察",
                auction_reasons=["free-stockdb暂无历史09:25竞价快照"],
                trend_reasons=_trend_reasons(row),
                risk_flags=risk_flags,
                data_quality=[str(flag) for flag in row.get("data_quality", [])],
            )
        )
    return items


class MorningAuctionWorkbenchService:
    def __init__(
        self,
        *,
        source: LivePredictionSource,
        model_path: Path,
        metadata_path: Path,
        lookback: int = 120,
        top_n: int = 3,
        max_items: int = 50,
    ) -> None:
        self._source = source
        self._model_path = model_path
        self._metadata_path = metadata_path
        self._lookback = lookback
        self._top_n = top_n
        self._max_items = max_items

    def predict(self, trade_date: str) -> MorningAuctionRun:
        rows, feature_end_date = build_live_prediction_rows(
            self._source,
            trade_date=trade_date,
            lookback=self._lookback,
        )
        scored_rows = score_rows_with_model(
            rows,
            model_path=self._model_path,
            metadata_path=self._metadata_path,
        )
        metadata = read_json(self._metadata_path)
        items = prediction_items_from_scored_rows(
            scored_rows,
            top_n=self._top_n,
            max_items=self._max_items,
        )
        return build_run(
            trade_date=trade_date,
            model_version=str(metadata.get("model_version", self._model_path.name)),
            source_status={
                "free_stockdb": "configured",
                "feature_end_date": feature_end_date,
                "auction_snapshot": "unavailable",
                "mode": "research_live_signal",
            },
            items=items,
        )


class MorningAuctionTrialStore:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._memory_log = MorningAuctionTrialLog()

    def list_entries(self, trade_date: str | None = None) -> list[MorningAuctionTrialEntry]:
        items = self._load().items
        if trade_date is not None:
            items = [entry for entry in items if entry.trade_date == trade_date]
        return sorted(items, key=lambda entry: (entry.trade_date, entry.rank or 9999, entry.symbol))

    def upsert(self, entry: MorningAuctionTrialEntry) -> MorningAuctionTrialEntry:
        normalized = entry.model_copy(update={"id": entry.id or self._entry_id(entry)})
        log = self._load()
        items = [item for item in log.items if item.id != normalized.id]
        items.append(normalized)
        self._save(MorningAuctionTrialLog(items=items))
        return normalized

    def _load(self) -> MorningAuctionTrialLog:
        if self._path.name == ":memory-not-used:":
            return self._memory_log
        if not self._path.exists():
            return MorningAuctionTrialLog()
        return MorningAuctionTrialLog.model_validate_json(self._path.read_text(encoding="utf-8"))

    def _save(self, log: MorningAuctionTrialLog) -> None:
        if self._path.name == ":memory-not-used:":
            self._memory_log = log
            return
        ensure_parent(self._path)
        self._path.write_text(log.model_dump_json(indent=2), encoding="utf-8")

    @staticmethod
    def _entry_id(entry: MorningAuctionTrialEntry) -> str:
        return f"{entry.trade_date}:{entry.symbol}"


def _previous_candidate_universe(
    source: LivePredictionSource,
    *,
    trade_date: str,
    max_calendar_backtrack: int,
) -> tuple[str, list[dict[str, object]]]:
    target = date.fromisoformat(trade_date)
    for days_back in range(1, max_calendar_backtrack + 1):
        candidate_date = (target - timedelta(days=days_back)).isoformat()
        candidates = source.candidate_universe(candidate_date)
        if candidates:
            return candidate_date, candidates
    raise ValueError(f"no candidate universe found before {trade_date}")


def _prefetch_daily_window_if_available(
    source: LivePredictionSource,
    *,
    feature_end_date: str,
    lookback: int,
) -> None:
    prefetch = getattr(source, "prefetch_daily_window", None)
    if callable(prefetch):
        prefetch(start_date=feature_end_date, end_date=feature_end_date, lookback=lookback)


def _data_quality_flags(auction: AuctionSnapshot | None) -> list[str]:
    flags = ["uses_previous_daily_bar"]
    if auction is None:
        flags.insert(0, "no_auction_snapshot")
    return flags


def _trend_reasons(row: dict[str, object]) -> list[str]:
    features = row.get("features")
    if not isinstance(features, dict):
        return []
    reasons: list[str] = []
    return_5d = features.get("return_5d")
    if isinstance(return_5d, int | float):
        reasons.append(f"5日涨幅{float(return_5d):.2f}%")
    amount_ratio_3d = features.get("amount_ratio_3d")
    if isinstance(amount_ratio_3d, int | float):
        reasons.append(f"3日成交额比{float(amount_ratio_3d):.2f}")
    return reasons


def _auction_return(auction: AuctionSnapshot | None) -> float | None:
    if auction is None or auction.indicative_price is None or auction.prev_close in (None, 0):
        return None
    return round((auction.indicative_price / auction.prev_close - 1) * 100, 4)


def _float_or_none(value: object) -> float | None:
    if value in (None, ""):
        return None
    return float(value)
