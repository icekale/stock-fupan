from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
import hashlib
import json
from typing import Any

from sqlalchemy import Engine, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.db.models import WatchlistAlertEvent, WatchlistStock
from app.db.session import session_scope


@dataclass
class WatchlistAlertInput:
    stock_id: int | None
    symbol: str
    name: str | None
    status: str
    groups: list[str]
    tags: list[str]
    entry_reason: str | None = None
    planned_buy_price: str | None = None
    invalid_condition: str | None = None
    themes: list[str] = field(default_factory=list)
    last_review_conclusion: str | None = None
    today_risk_hint: str | None = None
    quote: dict[str, Any] = field(default_factory=dict)
    metrics: dict[str, Any] = field(default_factory=dict)
    risk_signals: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class WatchlistAlertEventDTO:
    stock_id: int | None
    symbol: str
    name: str | None
    event_type: str
    severity: str
    status: str
    trigger_key: str
    payload_hash: str
    trigger_reason: str
    rule_snapshot: dict[str, Any]
    market_snapshot: dict[str, Any]
    source_status: dict[str, Any]
    notification_status: dict[str, Any]
    first_seen_at: datetime
    last_seen_at: datetime

    def model_dump(self, mode: str | None = None) -> dict[str, Any]:
        data = asdict(self)
        if mode == "json":
            data["first_seen_at"] = self.first_seen_at.isoformat()
            data["last_seen_at"] = self.last_seen_at.isoformat()
        return data


def build_watchlist_alert_events(
    items: list[WatchlistAlertInput],
    trade_date: str,
    mode: str,
    source_status: dict[str, Any],
    now: datetime,
) -> list[WatchlistAlertEventDTO]:
    events: list[WatchlistAlertEventDTO] = []
    for item in items:
        risk_event = _build_risk_event(item, trade_date, mode, source_status, now)
        if risk_event is not None:
            events.append(risk_event)
            continue
        opportunity_event = _build_opportunity_event(item, trade_date, mode, source_status, now)
        if opportunity_event is not None:
            events.append(opportunity_event)
    return events


def upsert_watchlist_alert_events(
    engine: Engine,
    events: list[WatchlistAlertEventDTO],
) -> list[WatchlistAlertEventDTO]:
    if not events:
        return []
    with session_scope(engine) as session:
        persisted: list[WatchlistAlertEventDTO] = []
        for event in events:
            normalized_event = _normalize_event_datetimes(event)
            if session.bind is not None and session.bind.dialect.name == "sqlite":
                stmt = sqlite_insert(WatchlistAlertEvent).values(
                    stock_id=normalized_event.stock_id,
                    symbol=normalized_event.symbol,
                    name=normalized_event.name,
                    event_type=normalized_event.event_type,
                    severity=normalized_event.severity,
                    status="active",
                    trigger_key=normalized_event.trigger_key,
                    payload_hash=normalized_event.payload_hash,
                    trigger_reason=normalized_event.trigger_reason,
                    ai_comment=None,
                    rule_snapshot=normalized_event.rule_snapshot,
                    market_snapshot=normalized_event.market_snapshot,
                    source_status=normalized_event.source_status,
                    notification_status=normalized_event.notification_status,
                    first_seen_at=normalized_event.first_seen_at,
                    last_seen_at=normalized_event.last_seen_at,
                )
                stmt = stmt.on_conflict_do_update(
                    index_elements=[
                        WatchlistAlertEvent.trigger_key,
                        WatchlistAlertEvent.payload_hash,
                    ],
                    set_={
                        "stock_id": normalized_event.stock_id,
                        "symbol": normalized_event.symbol,
                        "name": normalized_event.name,
                        "event_type": normalized_event.event_type,
                        "severity": normalized_event.severity,
                        "status": "active",
                        "trigger_reason": normalized_event.trigger_reason,
                        "rule_snapshot": normalized_event.rule_snapshot,
                        "market_snapshot": normalized_event.market_snapshot,
                        "source_status": normalized_event.source_status,
                        "notification_status": normalized_event.notification_status,
                        "last_seen_at": normalized_event.last_seen_at,
                    },
                )
                session.execute(stmt)
                row = (
                    session.execute(
                        select(WatchlistAlertEvent).where(
                            WatchlistAlertEvent.trigger_key == normalized_event.trigger_key,
                            WatchlistAlertEvent.payload_hash == normalized_event.payload_hash,
                        )
                    )
                    .scalars()
                    .one()
                )
                persisted.append(_row_to_dto(row))
                continue
            row = (
                session.execute(
                    select(WatchlistAlertEvent).where(
                        WatchlistAlertEvent.trigger_key == normalized_event.trigger_key,
                        WatchlistAlertEvent.payload_hash == normalized_event.payload_hash,
                    )
                )
                .scalars()
                .one_or_none()
            )
            if row is None:
                row = WatchlistAlertEvent(
                    stock_id=normalized_event.stock_id,
                    symbol=normalized_event.symbol,
                    name=normalized_event.name,
                    event_type=normalized_event.event_type,
                    severity=normalized_event.severity,
                    status="active",
                    trigger_key=normalized_event.trigger_key,
                    payload_hash=normalized_event.payload_hash,
                    trigger_reason=normalized_event.trigger_reason,
                    ai_comment=None,
                    rule_snapshot=normalized_event.rule_snapshot,
                    market_snapshot=normalized_event.market_snapshot,
                    source_status=normalized_event.source_status,
                    notification_status=normalized_event.notification_status,
                    first_seen_at=normalized_event.first_seen_at,
                    last_seen_at=normalized_event.last_seen_at,
                )
                session.add(row)
                session.flush()
            else:
                row.stock_id = normalized_event.stock_id
                row.symbol = normalized_event.symbol
                row.name = normalized_event.name
                row.event_type = normalized_event.event_type
                row.severity = normalized_event.severity
                row.status = "active"
                row.trigger_reason = normalized_event.trigger_reason
                row.rule_snapshot = normalized_event.rule_snapshot
                row.market_snapshot = normalized_event.market_snapshot
                row.source_status = normalized_event.source_status
                row.notification_status = normalized_event.notification_status
                row.last_seen_at = normalized_event.last_seen_at
                first_seen_at = _ensure_aware_datetime(row.first_seen_at)
                if first_seen_at is None or normalized_event.first_seen_at < first_seen_at:
                    row.first_seen_at = normalized_event.first_seen_at
            persisted.append(_row_to_dto(row))
        return persisted


def list_watchlist_alert_events(engine: Engine) -> list[dict[str, Any]]:
    with session_scope(engine) as session:
        rows = (
            session.execute(
                select(WatchlistAlertEvent).order_by(
                    WatchlistAlertEvent.last_seen_at.desc(),
                    WatchlistAlertEvent.id.desc(),
                )
            )
            .scalars()
            .all()
        )
        return [_row_to_dto(row).model_dump(mode="json") for row in rows]


def build_watchlist_alert_event_inputs(
    engine: Engine,
    *,
    stock_ids: list[int] | None = None,
) -> list[WatchlistAlertInput]:
    with session_scope(engine) as session:
        stmt = select(WatchlistStock).order_by(WatchlistStock.id)
        if stock_ids is not None:
            stmt = stmt.where(WatchlistStock.id.in_(stock_ids))
        stocks = session.execute(stmt).scalars().all()
        return [_stock_to_input(stock) for stock in stocks]


def _build_risk_event(
    item: WatchlistAlertInput,
    trade_date: str,
    mode: str,
    source_status: dict[str, Any],
    now: datetime,
) -> WatchlistAlertEventDTO | None:
    close = _float(item.metrics.get("close"))
    ma5 = _float(item.metrics.get("ma5"))
    pct_change = _float(item.quote.get("pct_change"))
    broke_ma5 = close is not None and ma5 is not None and close < ma5
    large_drop = pct_change is not None and pct_change <= -5
    if item.status != "持有中" or not (broke_ma5 or large_drop):
        return None
    reason_parts = []
    invalid_condition = _clean_text(item.invalid_condition)
    if invalid_condition:
        reason_parts.append(invalid_condition)
    if broke_ma5:
        reason_parts.append("跌破MA5")
    if large_drop:
        reason_parts.append("大跌")
    reason = "，".join(dict.fromkeys(reason_parts)) if reason_parts else "跌破MA5"
    market_snapshot = {
        "trade_date": trade_date,
        "mode": mode,
        "close": close,
        "ma5": ma5,
        "pct_change": pct_change,
    }
    return _event(
        item=item,
        event_type="risk",
        severity="high",
        rule_id="plan_invalid_or_ma_break",
        trigger_reason=reason,
        market_snapshot=market_snapshot,
        source_status=source_status,
        now=now,
    )


def _build_opportunity_event(
    item: WatchlistAlertInput,
    trade_date: str,
    mode: str,
    source_status: dict[str, Any],
    now: datetime,
) -> WatchlistAlertEventDTO | None:
    if item.status != "观察中":
        return None
    close = _float(item.metrics.get("close"))
    ma5 = _float(item.metrics.get("ma5"))
    volume_ratio_5d = _float(item.metrics.get("volume_ratio_5d"))
    sector_strength_score = _float(item.metrics.get("sector_strength_score"))
    if close is None or ma5 is None or close < ma5:
        return None
    if volume_ratio_5d is None or volume_ratio_5d < 1.8:
        return None
    market_snapshot = {
        "trade_date": trade_date,
        "mode": mode,
        "close": close,
        "ma5": ma5,
        "volume_ratio_5d": volume_ratio_5d,
        "sector_strength_score": sector_strength_score,
    }
    return _event(
        item=item,
        event_type="opportunity",
        severity="medium",
        rule_id="momentum_volume",
        trigger_reason="站上MA5且量能充足",
        market_snapshot=market_snapshot,
        source_status=source_status,
        now=now,
    )


def _event(
    item: WatchlistAlertInput,
    event_type: str,
    severity: str,
    rule_id: str,
    trigger_reason: str,
    market_snapshot: dict[str, Any],
    source_status: dict[str, Any],
    now: datetime,
) -> WatchlistAlertEventDTO:
    trigger_key = f"{item.symbol}:{event_type}:{rule_id}"
    payload_hash = _payload_hash(
        {
            "event_type": event_type,
            "rule_id": rule_id,
            "symbol": item.symbol,
            "trade_date": market_snapshot.get("trade_date"),
        }
    )
    rule_snapshot = {
        "rule_id": rule_id,
        "trade_mode": market_snapshot.get("mode"),
    }
    return WatchlistAlertEventDTO(
        stock_id=item.stock_id,
        symbol=item.symbol,
        name=item.name,
        event_type=event_type,
        severity=severity,
        status="active",
        trigger_key=trigger_key,
        payload_hash=payload_hash,
        trigger_reason=trigger_reason,
        rule_snapshot=rule_snapshot,
        market_snapshot=market_snapshot,
        source_status=source_status,
        notification_status={},
        first_seen_at=now,
        last_seen_at=now,
    )


def _row_to_dto(row: WatchlistAlertEvent) -> WatchlistAlertEventDTO:
    return WatchlistAlertEventDTO(
        stock_id=row.stock_id,
        symbol=row.symbol,
        name=row.name,
        event_type=row.event_type,
        severity=row.severity,
        status=row.status,
        trigger_key=row.trigger_key,
        payload_hash=row.payload_hash,
        trigger_reason=row.trigger_reason,
        rule_snapshot=row.rule_snapshot or {},
        market_snapshot=row.market_snapshot or {},
        source_status=row.source_status or {},
        notification_status=row.notification_status or {},
        first_seen_at=_as_utc(row.first_seen_at),
        last_seen_at=_as_utc(row.last_seen_at),
    )


def _stock_to_input(stock: WatchlistStock) -> WatchlistAlertInput:
    return WatchlistAlertInput(
        stock_id=stock.id,
        symbol=stock.symbol,
        name=stock.name,
        status="观察中",
        groups=[group.name for group in stock.groups],
        tags=stock.tags or [],
        entry_reason=stock.entry_reason,
        planned_buy_price=stock.planned_buy_price,
        invalid_condition=stock.invalid_condition,
        themes=stock.themes or [],
        last_review_conclusion=stock.last_review_conclusion,
        today_risk_hint=stock.today_risk_hint,
    )


def _payload_hash(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    return hashlib.sha256(raw).hexdigest()


def _clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _ensure_aware_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def _normalize_event_datetimes(event: WatchlistAlertEventDTO) -> WatchlistAlertEventDTO:
    return WatchlistAlertEventDTO(
        stock_id=event.stock_id,
        symbol=event.symbol,
        name=event.name,
        event_type=event.event_type,
        severity=event.severity,
        status=event.status,
        trigger_key=event.trigger_key,
        payload_hash=event.payload_hash,
        trigger_reason=event.trigger_reason,
        rule_snapshot=event.rule_snapshot,
        market_snapshot=event.market_snapshot,
        source_status=event.source_status,
        notification_status=event.notification_status,
        first_seen_at=_as_utc(event.first_seen_at),
        last_seen_at=_as_utc(event.last_seen_at),
    )
