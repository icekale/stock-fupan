import json
from pathlib import Path

import pytest

from app.db.models import WatchlistImport
from app.db.session import create_sqlite_engine, init_db, session_scope
from app.providers.ocr import FakeOcrProvider
from app.watchlist.ocr_service import (
    OcrPreviewNotFoundError,
    UnsupportedOcrImageError,
    WatchlistOcrService,
)
from app.watchlist.service import WatchlistImportService


def create_service(tmp_path: Path) -> tuple[WatchlistOcrService, object]:
    engine = create_sqlite_engine(f"sqlite:///{tmp_path / 'watchlist.db'}")
    init_db(engine)
    import_service = WatchlistImportService(engine=engine, snapshot_root=tmp_path / "watchlists")
    service = WatchlistOcrService(
        snapshot_root=tmp_path / "watchlists",
        ocr_provider=FakeOcrProvider(),
        import_service=import_service,
    )
    return service, engine


def test_ocr_preview_saves_artifacts_and_does_not_import(tmp_path: Path) -> None:
    service, engine = create_service(tmp_path)

    preview = service.create_preview(
        image_bytes=b"fake-png",
        mime_type="image/png",
        filename="watch.png",
    )

    assert preview.preview_id == "000001"
    assert preview.item_count == 3
    assert [item.symbol for item in preview.items] == ["600000.SH", "000001.SZ", "300750.SZ"]
    assert preview.provider_status == {
        "provider": "fake",
        "status": "success",
        "fallback_used": False,
        "reason": None,
    }
    assert Path(preview.image_snapshot_path).exists()
    assert Path(preview.ocr_text_snapshot_path).read_text(encoding="utf-8") == "600000\n000001\n300750"
    preview_json = json.loads(Path(preview.preview_snapshot_path).read_text(encoding="utf-8"))
    assert preview_json["preview_id"] == "000001"
    with session_scope(engine) as session:
        assert session.query(WatchlistImport).count() == 0


def test_ocr_confirm_imports_preview_text(tmp_path: Path) -> None:
    service, engine = create_service(tmp_path)
    preview = service.create_preview(b"fake-png", "image/png", "watch.png")

    imported = service.confirm_preview(preview.preview_id)

    assert imported.import_id == 1
    assert imported.item_count == 3
    assert [item.symbol for item in imported.items] == ["600000.SH", "000001.SZ", "300750.SZ"]
    with session_scope(engine) as session:
        assert session.query(WatchlistImport).count() == 1
        record = session.query(WatchlistImport).one()
        assert record.source_type == "text"
        assert record.source_name == "ocr:watch.png"


def test_ocr_preview_rejects_unsupported_mime_type(tmp_path: Path) -> None:
    service, _engine = create_service(tmp_path)

    with pytest.raises(UnsupportedOcrImageError, match="仅支持 PNG/JPEG/WebP 图片"):
        service.create_preview(b"text", "text/plain", "watch.txt")


def test_ocr_confirm_missing_preview_raises_not_found(tmp_path: Path) -> None:
    service, _engine = create_service(tmp_path)

    with pytest.raises(OcrPreviewNotFoundError, match="OCR 预览不存在"):
        service.confirm_preview("999999")
