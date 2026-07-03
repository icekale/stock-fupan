from __future__ import annotations

from collections.abc import Sequence
from uuid import uuid4

from app.services.morning_auction.features import FEATURE_VERSION
from app.services.morning_auction.schemas import (
    MorningAuctionBucket,
    MorningAuctionPredictionItem,
    MorningAuctionRun,
)


def bucket_prediction(
    *,
    prob_3pct: float,
    strong_5pct_score: float,
    risk_flags: Sequence[str],
) -> MorningAuctionBucket:
    if risk_flags:
        return MorningAuctionBucket.AVOID
    if prob_3pct >= 0.8:
        return MorningAuctionBucket.SELECTED
    if prob_3pct >= 0.65 and strong_5pct_score >= 0.8:
        return MorningAuctionBucket.ATTACK
    if prob_3pct >= 0.35:
        return MorningAuctionBucket.WATCH
    return MorningAuctionBucket.AVOID


def build_run(
    *,
    trade_date: str,
    model_version: str,
    source_status: dict[str, str],
    items: Sequence[MorningAuctionPredictionItem],
) -> MorningAuctionRun:
    selected_pool = [item for item in items if item.bucket == MorningAuctionBucket.SELECTED]
    attack_pool = [item for item in items if item.bucket == MorningAuctionBucket.ATTACK]
    watch_pool = [item for item in items if item.bucket == MorningAuctionBucket.WATCH]
    avoid_pool = [item for item in items if item.bucket == MorningAuctionBucket.AVOID]
    return MorningAuctionRun(
        run_id=uuid4().hex,
        trade_date=trade_date,
        model_version=model_version,
        feature_version=FEATURE_VERSION,
        source_status=source_status,
        selected_pool=selected_pool,
        attack_pool=attack_pool,
        watch_pool=watch_pool,
        avoid_pool=avoid_pool,
        items=list(items),
    )
