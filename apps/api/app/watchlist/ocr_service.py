import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from app.providers.ocr import OcrProvider
from app.services.assets import write_json
from app.watchlist.parser import WatchlistItem, parse_watchlist_text
from app.watchlist.service import WatchlistImportResult, WatchlistImportService


SUPPORTED_IMAGE_TYPES = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
}


class UnsupportedOcrImageError(ValueError):
    pass


class OcrPreviewNotFoundError(FileNotFoundError):
    pass


class WatchlistOcrPreviewResult(BaseModel):
    preview_id: str
    source_name: str
    item_count: int
    items: list[WatchlistItem]
    warnings: list[str]
    ocr_text: str
    provider_status: dict[str, Any]
    image_snapshot_path: str
    ocr_text_snapshot_path: str
    preview_snapshot_path: str


class WatchlistOcrService:
    def __init__(
        self,
        snapshot_root: Path,
        ocr_provider: OcrProvider,
        import_service: WatchlistImportService,
    ) -> None:
        self.snapshot_root = snapshot_root
        self.ocr_provider = ocr_provider
        self.import_service = import_service

    def create_preview(
        self,
        image_bytes: bytes,
        mime_type: str,
        filename: str | None,
    ) -> WatchlistOcrPreviewResult:
        extension = _extension_for_mime_type(mime_type)
        source_name = filename or f"upload{extension}"
        preview_id = self._next_preview_id()
        ocr_dir = self.snapshot_root / "ocr"
        ocr_dir.mkdir(parents=True, exist_ok=True)
        image_path = ocr_dir / f"{preview_id}-original{extension}"
        text_path = ocr_dir / f"{preview_id}-ocr.txt"
        preview_path = ocr_dir / f"{preview_id}-preview.json"

        image_path.write_bytes(image_bytes)
        ocr_result = self.ocr_provider.extract_text(image_bytes, mime_type, source_name)
        text_path.write_text(ocr_result.text, encoding="utf-8")
        parsed = parse_watchlist_text(ocr_result.text, source_name=f"ocr:{source_name}.txt")
        result = WatchlistOcrPreviewResult(
            preview_id=preview_id,
            source_name=source_name,
            item_count=len(parsed.items),
            items=parsed.items,
            warnings=parsed.warnings,
            ocr_text=ocr_result.text,
            provider_status={
                "provider": ocr_result.provider,
                "status": ocr_result.status,
                "fallback_used": ocr_result.fallback_used,
                "reason": ocr_result.reason,
            },
            image_snapshot_path=str(image_path),
            ocr_text_snapshot_path=str(text_path),
            preview_snapshot_path=str(preview_path),
        )
        write_json(preview_path, result.model_dump(mode="json"))
        return result

    def confirm_preview(self, preview_id: str) -> WatchlistImportResult:
        preview = self._load_preview(preview_id)
        return self.import_service.import_text(
            preview.ocr_text,
            source_name=f"ocr:{preview.source_name}",
        )

    def close(self) -> None:
        close = getattr(self.ocr_provider, "close", None)
        if callable(close):
            close()
        for child_name in ("primary", "fallback"):
            child = getattr(self.ocr_provider, child_name, None)
            child_close = getattr(child, "close", None)
            if callable(child_close):
                child_close()

    def _load_preview(self, preview_id: str) -> WatchlistOcrPreviewResult:
        preview_path = self.snapshot_root / "ocr" / f"{preview_id}-preview.json"
        if not preview_path.exists():
            raise OcrPreviewNotFoundError("OCR 预览不存在")
        payload = json.loads(preview_path.read_text(encoding="utf-8"))
        return WatchlistOcrPreviewResult.model_validate(payload)

    def _next_preview_id(self) -> str:
        ocr_dir = self.snapshot_root / "ocr"
        if not ocr_dir.exists():
            return "000001"
        latest = 0
        for path in ocr_dir.glob("*-preview.json"):
            prefix = path.name.split("-", 1)[0]
            if prefix.isdigit():
                latest = max(latest, int(prefix))
        return f"{latest + 1:06d}"


def _extension_for_mime_type(mime_type: str) -> str:
    normalized = mime_type.lower().split(";", 1)[0].strip()
    extension = SUPPORTED_IMAGE_TYPES.get(normalized)
    if extension is None:
        raise UnsupportedOcrImageError("仅支持 PNG/JPEG/WebP 图片")
    return extension
