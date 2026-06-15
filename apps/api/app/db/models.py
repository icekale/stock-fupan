from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Enum, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class ReportKindModel(StrEnum):
    CLOSE = "close"
    MIDDAY = "midday"
    WEEKLY = "weekly"


class ReportStatusModel(StrEnum):
    DRAFT = "draft"
    VALIDATION_FAILED = "validation_failed"
    READY_FOR_REVIEW = "ready_for_review"
    EXPORTED = "exported"


def _enum_values(enum_cls: type[StrEnum]) -> list[str]:
    return [member.value for member in enum_cls]


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trade_date: Mapped[str] = mapped_column(String(10), index=True)
    kind: Mapped[ReportKindModel] = mapped_column(
        Enum(ReportKindModel, values_callable=_enum_values), index=True
    )
    version: Mapped[str] = mapped_column(String(16))
    status: Mapped[ReportStatusModel] = mapped_column(
        Enum(ReportStatusModel, values_callable=_enum_values), index=True
    )
    asset_dir: Mapped[str] = mapped_column(String(1024))
    algorithm_versions: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    quality_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    publish_status: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    quality_summary: Mapped[str | None] = mapped_column(String(512), nullable=True)
    quality_gate: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


class RuntimeProviderConfig(Base):
    __tablename__ = "runtime_provider_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    market_provider: Mapped[str] = mapped_column(String(64))
    news_provider: Mapped[str] = mapped_column(String(64))
    review_sources: Mapped[list[str]] = mapped_column(JSON, default=list)
    fallback_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


class ReportScheduleConfig(Base):
    __tablename__ = "report_schedule_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    kind: Mapped[str] = mapped_column(String(16), default="close")
    time: Mapped[str] = mapped_column(String(5), default="19:00")
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Shanghai")
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_result: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


class WatchlistImport(Base):
    __tablename__ = "watchlist_imports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_type: Mapped[str] = mapped_column(String(32))
    source_name: Mapped[str] = mapped_column(String(255))
    snapshot_path: Mapped[str] = mapped_column(String(1024))
    parsed_snapshot_path: Mapped[str] = mapped_column(String(1024))
    item_count: Mapped[int] = mapped_column(Integer)
    warnings: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    items: Mapped[list["WatchlistItemModel"]] = relationship(
        back_populates="import_record",
        cascade="all, delete-orphan",
    )


class WatchlistItemModel(Base):
    __tablename__ = "watchlist_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    import_id: Mapped[int] = mapped_column(ForeignKey("watchlist_imports.id"), index=True)
    symbol: Mapped[str] = mapped_column(String(16), index=True)
    code: Mapped[str] = mapped_column(String(8), index=True)
    exchange: Mapped[str] = mapped_column(String(4))
    name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    display_order: Mapped[int] = mapped_column(Integer)
    import_record: Mapped[WatchlistImport] = relationship(back_populates="items")


class WatchlistStock(Base):
    __tablename__ = "watchlist_stocks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    code: Mapped[str] = mapped_column(String(8), index=True)
    exchange: Mapped[str] = mapped_column(String(4))
    name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    entry_reason: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    planned_buy_price: Mapped[str | None] = mapped_column(String(128), nullable=True)
    invalid_condition: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    themes: Mapped[list[str]] = mapped_column(JSON, default=list)
    last_review_conclusion: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    today_risk_hint: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
    groups: Mapped[list["WatchlistGroup"]] = relationship(
        secondary="watchlist_stock_groups",
        back_populates="stocks",
    )


class WatchlistGroup(Base):
    __tablename__ = "watchlist_groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
    stocks: Mapped[list[WatchlistStock]] = relationship(
        secondary="watchlist_stock_groups",
        back_populates="groups",
    )


class WatchlistStockGroup(Base):
    __tablename__ = "watchlist_stock_groups"
    __table_args__ = (UniqueConstraint("stock_id", "group_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("watchlist_stocks.id"), index=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("watchlist_groups.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
