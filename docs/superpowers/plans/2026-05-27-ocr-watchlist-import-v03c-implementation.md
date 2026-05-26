# OCR Watchlist Import v0.3c Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add image-based OCR watchlist preview and explicit confirmation so screenshot-derived stocks can feed the existing HTML report `自选股观察` path.

**Architecture:** OCR is a pre-import ingestion layer. Uploading an image creates local preview artifacts and parses OCR text with the existing watchlist parser; only confirmation calls `WatchlistImportService.import_text`, keeping SQLite and HTML report behavior on the existing path.

**Tech Stack:** FastAPI multipart uploads, Pydantic DTOs, local file snapshots, OpenAI-compatible vision API, deterministic fake provider, React/Next.js TypeScript UI, pytest, `tsc --noEmit`, ruff.

---

## File Structure

- Create `apps/api/app/providers/ocr.py`: OCR DTOs, provider protocol, fake provider, OpenAI-compatible provider, fallback wrapper.
- Modify `apps/api/app/providers/factory.py`: include OCR provider in `ProviderBundle` and factory creation.
- Modify `apps/api/app/config.py`: add OCR provider settings.
- Create `apps/api/app/watchlist/ocr_service.py`: preview persistence, MIME validation, preview loading, confirm-to-import orchestration.
- Modify `apps/api/app/main.py`: add `ocr-preview` and `ocr-confirm` routes and request DTO.
- Create `apps/api/tests/test_ocr_provider.py`: provider and fallback behavior.
- Create `apps/api/tests/test_watchlist_ocr_api.py`: service/API behavior and persistence.
- Modify `apps/web/lib/types.ts`: add OCR preview result types.
- Modify `apps/web/lib/api.ts`: add OCR preview and confirm helpers.
- Modify `apps/web/components/WatchlistImportPanel.tsx`: add screenshot upload preview/confirm UI.
- Modify `.env.example`: add OCR environment settings.
- Modify `README.md`: document OCR import workflow.

---

### Task 1: Add OCR Provider Boundary

**Files:**
- Create: `apps/api/app/providers/ocr.py`
- Create: `apps/api/tests/test_ocr_provider.py`

- [ ] **Step 1: Write failing provider tests**

Create `apps/api/tests/test_ocr_provider.py`:

```python
import pytest

from app.providers.ocr import (
    FakeOcrProvider,
    FallbackOcrProvider,
    OcrExtractError,
    OcrExtractResult,
)


class BrokenOcrProvider:
    def extract_text(self, image_bytes: bytes, mime_type: str, filename: str) -> OcrExtractResult:
        raise OcrExtractError("vision unavailable")


class EmptyOcrProvider:
    def extract_text(self, image_bytes: bytes, mime_type: str, filename: str) -> OcrExtractResult:
        return OcrExtractResult(
            text="",
            provider="empty",
            status="success",
            fallback_used=False,
            reason=None,
        )


def test_fake_ocr_provider_returns_deterministic_watchlist_text() -> None:
    result = FakeOcrProvider().extract_text(b"fake-image", "image/png", "watch.png")

    assert result.text == "600000\n000001\n300750"
    assert result.provider == "fake"
    assert result.status == "success"
    assert result.fallback_used is False
    assert result.reason is None


def test_fallback_ocr_provider_uses_fake_when_primary_fails() -> None:
    result = FallbackOcrProvider(
        primary=BrokenOcrProvider(),
        fallback=FakeOcrProvider(),
        fallback_enabled=True,
    ).extract_text(b"fake-image", "image/png", "watch.png")

    assert result.text == "600000\n000001\n300750"
    assert result.provider == "fake"
    assert result.status == "fallback"
    assert result.fallback_used is True
    assert result.reason == "vision unavailable"


def test_fallback_ocr_provider_raises_when_fallback_disabled() -> None:
    provider = FallbackOcrProvider(
        primary=BrokenOcrProvider(),
        fallback=FakeOcrProvider(),
        fallback_enabled=False,
    )

    with pytest.raises(OcrExtractError, match="vision unavailable"):
        provider.extract_text(b"fake-image", "image/png", "watch.png")


def test_fallback_ocr_provider_rejects_empty_primary_text() -> None:
    result = FallbackOcrProvider(
        primary=EmptyOcrProvider(),
        fallback=FakeOcrProvider(),
        fallback_enabled=True,
    ).extract_text(b"fake-image", "image/png", "watch.png")

    assert result.status == "fallback"
    assert result.reason == "OCR 未识别出文本"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd apps/api && uv run pytest tests/test_ocr_provider.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'app.providers.ocr'`.

- [ ] **Step 3: Implement OCR provider module**

Create `apps/api/app/providers/ocr.py`:

```python
import base64
from typing import Literal, Protocol

from openai import OpenAI
from pydantic import BaseModel


class OcrExtractError(RuntimeError):
    pass


class OcrExtractResult(BaseModel):
    text: str
    provider: str
    status: Literal["success", "fallback"] = "success"
    fallback_used: bool = False
    reason: str | None = None


class OcrProvider(Protocol):
    def extract_text(self, image_bytes: bytes, mime_type: str, filename: str) -> OcrExtractResult:
        pass


class FakeOcrProvider:
    def extract_text(self, image_bytes: bytes, mime_type: str, filename: str) -> OcrExtractResult:
        return OcrExtractResult(
            text="600000\n000001\n300750",
            provider="fake",
            status="success",
            fallback_used=False,
            reason=None,
        )


class OpenAIVisionOcrProvider:
    def __init__(self, api_key: str, base_url: str, model_name: str, timeout_seconds: float) -> None:
        self.api_key = api_key
        self.base_url = base_url
        self.model_name = model_name
        self.timeout_seconds = timeout_seconds
        self.client = OpenAI(api_key=api_key or "missing", base_url=base_url, timeout=timeout_seconds)

    def extract_text(self, image_bytes: bytes, mime_type: str, filename: str) -> OcrExtractResult:
        if not self.api_key:
            raise OcrExtractError("OPENAI_API_KEY 未配置")
        data_url = f"data:{mime_type};base64,{base64.b64encode(image_bytes).decode('ascii')}"
        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": (
                                    "请从这张股票软件截图中提取所有 A 股股票代码和名称。"
                                    "只输出纯文本，每行一个股票，尽量保留代码和名称，不要解释。"
                                ),
                            },
                            {"type": "image_url", "image_url": {"url": data_url}},
                        ],
                    }
                ],
                temperature=0,
            )
        except Exception as exc:
            raise OcrExtractError(f"OCR 请求失败: {exc.__class__.__name__}") from exc
        text = response.choices[0].message.content or ""
        if not text.strip():
            raise OcrExtractError("OCR 未识别出文本")
        return OcrExtractResult(
            text=text.strip(),
            provider="openai",
            status="success",
            fallback_used=False,
            reason=None,
        )

    def close(self) -> None:
        close = getattr(self.client, "close", None)
        if callable(close):
            close()


class FallbackOcrProvider:
    def __init__(self, primary: OcrProvider, fallback: OcrProvider, fallback_enabled: bool) -> None:
        self.primary = primary
        self.fallback = fallback
        self.fallback_enabled = fallback_enabled

    def extract_text(self, image_bytes: bytes, mime_type: str, filename: str) -> OcrExtractResult:
        try:
            result = self.primary.extract_text(image_bytes, mime_type, filename)
            if not result.text.strip():
                raise OcrExtractError("OCR 未识别出文本")
            return result
        except OcrExtractError as exc:
            if not self.fallback_enabled:
                raise
            fallback_result = self.fallback.extract_text(image_bytes, mime_type, filename)
            return OcrExtractResult(
                text=fallback_result.text,
                provider=fallback_result.provider,
                status="fallback",
                fallback_used=True,
                reason=str(exc),
            )
```

- [ ] **Step 4: Run provider tests**

Run:

```bash
cd apps/api && uv run pytest tests/test_ocr_provider.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit provider boundary**

```bash
git add apps/api/app/providers/ocr.py apps/api/tests/test_ocr_provider.py
git commit -m "feat: add ocr provider boundary"
```

---

### Task 2: Add OCR Preview Service

**Files:**
- Create: `apps/api/app/watchlist/ocr_service.py`
- Create: `apps/api/tests/test_watchlist_ocr_api.py`

- [ ] **Step 1: Write failing service tests**

Create `apps/api/tests/test_watchlist_ocr_api.py`:

```python
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
```

- [ ] **Step 2: Run service tests to verify failure**

Run:

```bash
cd apps/api && uv run pytest tests/test_watchlist_ocr_api.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'app.watchlist.ocr_service'`.

- [ ] **Step 3: Implement OCR preview service**

Create `apps/api/app/watchlist/ocr_service.py`:

```python
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
```

- [ ] **Step 4: Run service tests**

Run:

```bash
cd apps/api && uv run pytest tests/test_watchlist_ocr_api.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit OCR preview service**

```bash
git add apps/api/app/watchlist/ocr_service.py apps/api/tests/test_watchlist_ocr_api.py
git commit -m "feat: add ocr watchlist preview service"
```

---

### Task 3: Wire OCR Provider Factory and API Routes

**Files:**
- Modify: `apps/api/app/config.py`
- Modify: `apps/api/app/providers/factory.py`
- Modify: `apps/api/app/main.py`
- Modify: `apps/api/tests/test_watchlist_ocr_api.py`

- [ ] **Step 1: Extend API tests for routes**

Append to `apps/api/tests/test_watchlist_ocr_api.py`:

```python
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app


def test_ocr_preview_api_returns_preview_without_importing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'api.db'}")
    monkeypatch.setenv("WATCHLIST_SNAPSHOT_ROOT", str(tmp_path / "watchlists"))
    monkeypatch.setenv("OCR_PROVIDER", "fake")
    get_settings.cache_clear()

    with TestClient(app) as client:
        response = client.post(
            "/api/watchlists/ocr-preview",
            files={"file": ("watch.png", b"fake-png", "image/png")},
        )
        latest_response = client.get("/api/watchlists/latest")

    assert response.status_code == 200
    payload = response.json()
    assert payload["preview_id"] == "000001"
    assert payload["item_count"] == 3
    assert [item["symbol"] for item in payload["items"]] == ["600000.SH", "000001.SZ", "300750.SZ"]
    assert latest_response.json()["item_count"] == 0
    get_settings.cache_clear()


def test_ocr_confirm_api_imports_preview(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'api.db'}")
    monkeypatch.setenv("WATCHLIST_SNAPSHOT_ROOT", str(tmp_path / "watchlists"))
    monkeypatch.setenv("OCR_PROVIDER", "fake")
    get_settings.cache_clear()

    with TestClient(app) as client:
        preview_response = client.post(
            "/api/watchlists/ocr-preview",
            files={"file": ("watch.png", b"fake-png", "image/png")},
        )
        response = client.post(
            "/api/watchlists/ocr-confirm",
            json={"preview_id": preview_response.json()["preview_id"]},
        )
        latest_response = client.get("/api/watchlists/latest")

    assert response.status_code == 200
    payload = response.json()
    assert payload["item_count"] == 3
    assert latest_response.json()["item_count"] == 3
    get_settings.cache_clear()


def test_ocr_preview_api_rejects_unsupported_file_type(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'api.db'}")
    monkeypatch.setenv("WATCHLIST_SNAPSHOT_ROOT", str(tmp_path / "watchlists"))
    monkeypatch.setenv("OCR_PROVIDER", "fake")
    get_settings.cache_clear()

    with TestClient(app) as client:
        response = client.post(
            "/api/watchlists/ocr-preview",
            files={"file": ("watch.txt", b"600000", "text/plain")},
        )

    assert response.status_code == 400
    assert "仅支持 PNG/JPEG/WebP 图片" in response.json()["detail"]
    get_settings.cache_clear()


def test_ocr_confirm_api_returns_404_for_missing_preview(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'api.db'}")
    monkeypatch.setenv("WATCHLIST_SNAPSHOT_ROOT", str(tmp_path / "watchlists"))
    monkeypatch.setenv("OCR_PROVIDER", "fake")
    get_settings.cache_clear()

    with TestClient(app) as client:
        response = client.post("/api/watchlists/ocr-confirm", json={"preview_id": "999999"})

    assert response.status_code == 404
    assert "OCR 预览不存在" in response.json()["detail"]
    get_settings.cache_clear()
```

- [ ] **Step 2: Run route tests to verify failure**

Run:

```bash
cd apps/api && uv run pytest tests/test_watchlist_ocr_api.py -q
```

Expected: FAIL with 404 for `/api/watchlists/ocr-preview` and `/api/watchlists/ocr-confirm`.

- [ ] **Step 3: Add OCR settings**

Modify `apps/api/app/config.py` inside `Settings` after `llm_provider`:

```python
    ocr_provider: str = "fake"
    ocr_fallback_enabled: bool = True
    ocr_model: str = "gpt-4.1-mini"
```

- [ ] **Step 4: Wire OCR provider factory**

Modify `apps/api/app/providers/factory.py` imports:

```python
from app.providers.ocr import (
    FakeOcrProvider,
    FallbackOcrProvider,
    OcrProvider,
    OpenAIVisionOcrProvider,
)
```

Add field to `ProviderBundle`:

```python
    ocr_provider: OcrProvider
```

Add to `close()` before tickflow or after llm:

```python
        _close_provider(self.ocr_provider)
```

Add to `create_provider_bundle`:

```python
        ocr_provider=_create_ocr_provider(settings),
```

Add factory function after `_create_llm_provider`:

```python
def _create_ocr_provider(settings: Settings) -> OcrProvider:
    if settings.ocr_provider == "fake":
        return FakeOcrProvider()
    if settings.ocr_provider == "openai":
        return FallbackOcrProvider(
            primary=OpenAIVisionOcrProvider(
                api_key=settings.openai_api_key,
                base_url=settings.openai_base_url,
                model_name=settings.ocr_model,
                timeout_seconds=settings.provider_timeout_seconds,
            ),
            fallback=FakeOcrProvider(),
            fallback_enabled=settings.ocr_fallback_enabled,
        )
    raise ValueError(f"Unsupported OCR_PROVIDER: {settings.ocr_provider}")
```

- [ ] **Step 5: Add OCR API routes**

Modify `apps/api/app/main.py` imports:

```python
from fastapi import FastAPI, HTTPException, UploadFile
from app.providers.ocr import OcrExtractError
from app.watchlist.ocr_service import (
    OcrPreviewNotFoundError,
    UnsupportedOcrImageError,
    WatchlistOcrService,
)
```

Add request DTO near other request classes:

```python
class ConfirmOcrPreviewRequest(BaseModel):
    preview_id: str
```

Add service helper after `_watchlist_service()`:

```python
def _watchlist_ocr_service() -> WatchlistOcrService:
    settings = get_settings()
    providers = create_provider_bundle(settings)
    return WatchlistOcrService(
        snapshot_root=Path(settings.watchlist_snapshot_root),
        ocr_provider=providers.ocr_provider,
        import_service=_watchlist_service(),
    )
```

Add a `close()` method to `WatchlistOcrService` in `ocr_service.py`:

```python
    def close(self) -> None:
        close = getattr(self.ocr_provider, "close", None)
        if callable(close):
            close()
        for child_name in ("primary", "fallback"):
            child = getattr(self.ocr_provider, child_name, None)
            child_close = getattr(child, "close", None)
            if callable(child_close):
                child_close()
```

Add routes before latest endpoint. Do not import private factory helpers into `main.py`:

```python
@app.post("/api/watchlists/ocr-preview")
async def preview_watchlist_ocr(file: UploadFile) -> dict[str, object]:
    service = _watchlist_ocr_service()
    try:
        result = service.create_preview(
            image_bytes=await file.read(),
            mime_type=file.content_type or "application/octet-stream",
            filename=file.filename,
        )
    except UnsupportedOcrImageError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OcrExtractError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    finally:
        service.close()
    return result.model_dump(mode="json")


@app.post("/api/watchlists/ocr-confirm")
def confirm_watchlist_ocr(request: ConfirmOcrPreviewRequest) -> dict[str, object]:
    service = _watchlist_ocr_service()
    try:
        result = service.confirm_preview(request.preview_id)
    except OcrPreviewNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    finally:
        service.close()
    return result.model_dump(mode="json")
```

- [ ] **Step 6: Run OCR route tests**

Run:

```bash
cd apps/api && uv run pytest tests/test_watchlist_ocr_api.py -q
```

Expected: PASS.

- [ ] **Step 7: Run related backend tests**

Run:

```bash
cd apps/api && uv run pytest tests/test_ocr_provider.py tests/test_watchlist_ocr_api.py tests/test_watchlist_api.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit API routes**

```bash
git add apps/api/app/config.py apps/api/app/providers/factory.py apps/api/app/main.py apps/api/app/watchlist/ocr_service.py apps/api/tests/test_watchlist_ocr_api.py
git commit -m "feat: expose ocr watchlist api"
```

---

### Task 4: Add Frontend OCR Preview and Confirm UI

**Files:**
- Modify: `apps/web/lib/types.ts`
- Modify: `apps/web/lib/api.ts`
- Modify: `apps/web/components/WatchlistImportPanel.tsx`

- [ ] **Step 1: Add TypeScript types**

Modify `apps/web/lib/types.ts` after `WatchlistImportResult`:

```ts
export type OcrProviderStatus = {
  provider: string;
  status: "success" | "fallback";
  fallback_used: boolean;
  reason: string | null;
};

export type WatchlistOcrPreviewResult = {
  preview_id: string;
  source_name: string;
  item_count: number;
  items: WatchlistItem[];
  warnings: string[];
  ocr_text: string;
  provider_status: OcrProviderStatus;
  image_snapshot_path: string;
  ocr_text_snapshot_path: string;
  preview_snapshot_path: string;
};
```

- [ ] **Step 2: Add API helpers**

Modify `apps/web/lib/api.ts` import:

```ts
import type { CreateReportResponse, WatchlistImportResult, WatchlistOcrPreviewResult } from "./types";
```

Add after `importWatchlistFile`:

```ts
export async function previewWatchlistOcr(file: File): Promise<WatchlistOcrPreviewResult> {
  const formData = new FormData();
  formData.append("file", file);
  const response = await fetch(`${API_BASE_URL}/api/watchlists/ocr-preview`, {
    method: "POST",
    body: formData,
  });
  if (!response.ok) {
    throw new Error(`OCR 识别失败：${response.status} ${await response.text()}`);
  }
  return response.json() as Promise<WatchlistOcrPreviewResult>;
}

export async function confirmWatchlistOcr(previewId: string): Promise<WatchlistImportResult> {
  const response = await fetch(`${API_BASE_URL}/api/watchlists/ocr-confirm`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ preview_id: previewId }),
  });
  if (!response.ok) {
    throw new Error(`OCR 导入失败：${response.status} ${await response.text()}`);
  }
  return response.json() as Promise<WatchlistImportResult>;
}
```

- [ ] **Step 3: Extend watchlist panel state and handlers**

Modify `apps/web/components/WatchlistImportPanel.tsx` imports:

```ts
import { confirmWatchlistOcr, importWatchlistFile, importWatchlistText, previewWatchlistOcr } from "../lib/api";
import type { WatchlistImportResult, WatchlistOcrPreviewResult } from "../lib/types";
```

Add state after `latest`:

```ts
  const [ocrPreview, setOcrPreview] = useState<WatchlistOcrPreviewResult | null>(null);
  const [confirmingOcr, setConfirmingOcr] = useState(false);
```

Add handlers before `return`:

```ts
  async function handleOcrFileChange(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    setRunning(true);
    setError(null);
    try {
      const result = await previewWatchlistOcr(file);
      setOcrPreview(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "OCR 识别失败");
    } finally {
      setRunning(false);
      event.target.value = "";
    }
  }

  async function handleConfirmOcr() {
    if (!ocrPreview) return;
    setConfirmingOcr(true);
    setError(null);
    try {
      const result = await confirmWatchlistOcr(ocrPreview.preview_id);
      setLatest(result);
      setOcrPreview(null);
      onImported(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "OCR 导入失败");
    } finally {
      setConfirmingOcr(false);
    }
  }
```

- [ ] **Step 4: Add OCR controls to JSX**

Change the upload grid from two columns to three on larger screens:

```tsx
      <div className="mt-3 grid gap-2 sm:grid-cols-3">
```

Add third label inside that grid:

```tsx
        <label className="cursor-pointer rounded-2xl border border-slate-200 px-4 py-2.5 text-center text-sm font-bold text-slate-700 hover:border-slate-300">
          上传截图识别
          <input
            className="hidden"
            type="file"
            accept=".png,.jpg,.jpeg,.webp,image/png,image/jpeg,image/webp"
            onChange={handleOcrFileChange}
          />
        </label>
```

Add preview block after `{error && ...}` and before `{latest && ...}`:

```tsx
      {ocrPreview && (
        <div className="mt-3 rounded-2xl border border-amber-200 bg-amber-50 p-3 text-xs leading-6 text-amber-900">
          <div className="flex items-center justify-between gap-2">
            <div className="font-bold">OCR 识别预览 · {ocrPreview.item_count} 只</div>
            <span className="rounded-full bg-white/70 px-2 py-0.5 text-[11px] font-semibold text-amber-700">
              {ocrPreview.provider_status.provider}
              {ocrPreview.provider_status.fallback_used ? " fallback" : ""}
            </span>
          </div>
          <div className="mt-1 line-clamp-3 text-amber-800">
            {ocrPreview.items.map((item) => item.symbol).join("、") || "未识别到股票代码"}
          </div>
          {ocrPreview.warnings.length > 0 && <div className="mt-1 text-amber-700">{ocrPreview.warnings.join("；")}</div>}
          <details className="mt-2">
            <summary className="cursor-pointer font-semibold">查看 OCR 文本</summary>
            <pre className="mt-2 max-h-28 overflow-auto whitespace-pre-wrap rounded-xl bg-white/70 p-2 text-[11px] text-slate-700">
              {ocrPreview.ocr_text}
            </pre>
          </details>
          <button
            className="mt-3 w-full rounded-2xl bg-amber-600 px-4 py-2.5 text-sm font-bold text-white disabled:bg-amber-300"
            disabled={confirmingOcr}
            onClick={handleConfirmOcr}
            type="button"
          >
            {confirmingOcr ? "确认中..." : "确认导入 OCR 结果"}
          </button>
        </div>
      )}
```

- [ ] **Step 5: Run frontend type check**

Run:

```bash
corepack pnpm --filter @stock-review/web test
```

Expected: PASS.

- [ ] **Step 6: Commit frontend OCR UI**

```bash
git add apps/web/lib/types.ts apps/web/lib/api.ts apps/web/components/WatchlistImportPanel.tsx
git commit -m "feat: add ocr watchlist import ui"
```

---

### Task 5: Document OCR Configuration

**Files:**
- Modify: `.env.example`
- Modify: `README.md`

- [ ] **Step 1: Update `.env.example`**

Add after `LLM_PROVIDER=fake`:

```dotenv
OCR_PROVIDER=fake
OCR_FALLBACK_ENABLED=true
OCR_MODEL=gpt-4.1-mini
```

- [ ] **Step 2: Update README**

Add after `Watchlist and TickFlow Enrichment` section:

```markdown
## OCR Watchlist Import

v0.3c supports screenshot-based watchlist import. Uploading an image creates an OCR preview first; the latest SQLite watchlist is updated only after clicking confirm.

```dotenv
OCR_PROVIDER=fake
OCR_FALLBACK_ENABLED=true
OCR_MODEL=gpt-4.1-mini
```

Behavior:

- Supported image uploads: PNG, JPEG, and WebP.
- `OCR_PROVIDER=fake` returns deterministic local data for offline development and tests.
- `OCR_PROVIDER=openai` uses the existing OpenAI-compatible `OPENAI_API_KEY` and `OPENAI_BASE_URL` settings with `OCR_MODEL`.
- OCR preview artifacts are stored under `WATCHLIST_SNAPSHOT_ROOT/ocr`.
- Confirmed OCR imports reuse the normal watchlist import path and appear in generated HTML reports through `自选股观察`.
- API keys are read only from local environment variables and are not written to snapshots or generated report assets.
```

- [ ] **Step 3: Run docs diff check**

Run:

```bash
git diff --check
```

Expected: no output.

- [ ] **Step 4: Commit docs**

```bash
git add .env.example README.md
git commit -m "docs: document ocr watchlist import"
```

---

### Task 6: Full Verification and Local Merge

**Files:**
- No new files expected unless fixes are required.

- [ ] **Step 1: Run backend tests**

Run:

```bash
cd apps/api && uv run pytest -q
```

Expected: all tests pass.

- [ ] **Step 2: Run backend lint**

Run:

```bash
cd apps/api && uv run ruff check .
```

Expected: PASS.

- [ ] **Step 3: Run frontend test/lint**

Run:

```bash
corepack pnpm --filter @stock-review/web test
corepack pnpm --filter @stock-review/web lint
```

Expected: PASS.

- [ ] **Step 4: Run fake OCR smoke through API**

Run API in one terminal:

```bash
cd apps/api
DATABASE_URL=sqlite:///./data/ocr-smoke.db WATCHLIST_SNAPSHOT_ROOT=./data/watchlists-smoke OCR_PROVIDER=fake uv run uvicorn app.main:app --port 8010
```

Run smoke requests in another terminal:

```bash
printf 'fake-png' > /tmp/watch.png
curl -s -F 'file=@/tmp/watch.png;type=image/png' http://127.0.0.1:8010/api/watchlists/ocr-preview > /tmp/ocr-preview.json
python - <<'PY'
import json, urllib.request
payload = json.load(open('/tmp/ocr-preview.json'))
assert payload['item_count'] == 3, payload
request = urllib.request.Request(
    'http://127.0.0.1:8010/api/watchlists/ocr-confirm',
    data=json.dumps({'preview_id': payload['preview_id']}).encode(),
    headers={'Content-Type': 'application/json'},
    method='POST',
)
confirmed = json.loads(urllib.request.urlopen(request).read())
assert confirmed['item_count'] == 3, confirmed
print('OCR smoke OK', payload['preview_id'])
PY
```

Expected: prints `OCR smoke OK 000001`.

- [ ] **Step 5: Secret scan**

Run:

```bash
git grep -n "TICKFLOW_KEY_PLACEHOLDER\|ANSPIRE_KEY_PLACEHOLDER" -- . ':!docs/superpowers/plans/2026-05-27-ocr-watchlist-import-v03c-implementation.md'
```

Expected: no output. If any output appears, remove the secret before proceeding.

- [ ] **Step 6: Merge back to main locally after verification passes**

Run from original main worktree:

```bash
cd "/Users/kale/Documents/stock fupan"
git status --short
git merge --no-ff codex/ocr-watchlist-import-v03c -m "merge: ocr watchlist import v0.3c"
git status --short --branch
```

Expected: merge succeeds and `main` is clean.

---

## Plan Self-Review

- Spec coverage: provider boundary, preview storage, confirmation flow, API, frontend UI, docs, tests, and HTML path preservation are covered.
- Placeholder scan: no `TBD`, `TODO`, `implement later`, or vague test-only instructions remain.
- Type consistency: backend DTO names use `WatchlistOcrPreviewResult`; frontend uses `WatchlistOcrPreviewResult`; API endpoints use `/api/watchlists/ocr-preview` and `/api/watchlists/ocr-confirm` consistently.
- Scope check: no cropping/editor/auto-import/report-image embedding is included.
