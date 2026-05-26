from pathlib import Path

from pydantic import BaseModel
from sqlalchemy import Engine, select

from app.db.models import WatchlistImport, WatchlistItemModel
from app.db.session import session_scope
from app.services.assets import write_json
from app.watchlist.parser import WatchlistItem, parse_watchlist_text


class WatchlistImportResult(BaseModel):
    import_id: int | None
    item_count: int
    items: list[WatchlistItem]
    warnings: list[str] = []


class WatchlistImportService:
    def __init__(self, engine: Engine, snapshot_root: Path) -> None:
        self.engine = engine
        self.snapshot_root = snapshot_root

    def import_text(self, content: str, source_name: str = "manual.txt") -> WatchlistImportResult:
        parsed = parse_watchlist_text(content, source_name=source_name)
        imports_dir = self.snapshot_root / "imports"
        imports_dir.mkdir(parents=True, exist_ok=True)
        next_id = self._next_import_id()
        safe_name = _safe_filename(source_name)
        raw_path = imports_dir / f"{next_id:06d}-{safe_name}"
        parsed_path = imports_dir / f"{next_id:06d}-parsed.json"
        raw_path.write_text(content, encoding="utf-8")
        write_json(parsed_path, parsed.model_dump(mode="json"))

        with session_scope(self.engine) as session:
            record = WatchlistImport(
                source_type="text",
                source_name=source_name,
                snapshot_path=str(raw_path),
                parsed_snapshot_path=str(parsed_path),
                item_count=len(parsed.items),
                warnings=parsed.warnings,
            )
            session.add(record)
            session.flush()
            for index, item in enumerate(parsed.items):
                session.add(
                    WatchlistItemModel(
                        import_id=record.id,
                        symbol=item.symbol,
                        code=item.code,
                        exchange=item.exchange,
                        name=item.name,
                        display_order=index,
                    )
                )
            import_id = record.id

        return WatchlistImportResult(
            import_id=import_id,
            item_count=len(parsed.items),
            items=parsed.items,
            warnings=parsed.warnings,
        )

    def get_latest(self) -> WatchlistImportResult:
        with session_scope(self.engine) as session:
            record = session.execute(
                select(WatchlistImport).order_by(WatchlistImport.id.desc()).limit(1)
            ).scalar_one_or_none()
            if record is None:
                return WatchlistImportResult(import_id=None, item_count=0, items=[], warnings=[])
            rows = (
                session.execute(
                    select(WatchlistItemModel)
                    .where(WatchlistItemModel.import_id == record.id)
                    .order_by(WatchlistItemModel.display_order)
                )
                .scalars()
                .all()
            )
            items = [
                WatchlistItem(
                    symbol=row.symbol,
                    code=row.code,
                    exchange=row.exchange,  # type: ignore[arg-type]
                    name=row.name,
                )
                for row in rows
            ]
            return WatchlistImportResult(
                import_id=record.id,
                item_count=len(items),
                items=items,
                warnings=record.warnings or [],
            )

    def _next_import_id(self) -> int:
        with session_scope(self.engine) as session:
            latest = session.execute(
                select(WatchlistImport.id).order_by(WatchlistImport.id.desc()).limit(1)
            ).scalar_one_or_none()
            return int(latest or 0) + 1


def _safe_filename(name: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in {".", "-", "_"} else "_" for ch in name)
    return cleaned or "watchlist.txt"
