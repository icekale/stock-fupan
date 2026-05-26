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
    def __init__(
        self,
        api_key: str,
        base_url: str,
        model_name: str,
        timeout_seconds: float,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url
        self.model_name = model_name
        self.timeout_seconds = timeout_seconds
        self.client = OpenAI(
            api_key=api_key or "missing",
            base_url=base_url,
            timeout=timeout_seconds,
        )

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
