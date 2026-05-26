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
