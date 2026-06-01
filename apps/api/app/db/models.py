from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class ReportKindModel(StrEnum):
    CLOSE = "close"
    MIDDAY = "midday"


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


class EvidenceRecord(Base):
    __tablename__ = "evidence_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    evidence_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    trade_date: Mapped[str] = mapped_column(String(10), index=True)
    source: Mapped[str] = mapped_column(String(128))
    title: Mapped[str] = mapped_column(String(512))
    url: Mapped[str] = mapped_column(String(1024))
    published_at: Mapped[str] = mapped_column(String(64))
    category: Mapped[str] = mapped_column(String(32), index=True)
    claim: Mapped[str] = mapped_column(String(1024))
    numbers: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    related_sectors: Mapped[list[str]] = mapped_column(JSON, default=list)
    confidence: Mapped[str] = mapped_column(String(16), index=True)
    status: Mapped[str] = mapped_column(String(16), index=True)
    manual_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
