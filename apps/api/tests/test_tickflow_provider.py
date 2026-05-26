import httpx
import pytest

from app.providers.market import ProviderFallbackError
from app.providers.tickflow import FallbackTickFlowProvider, FakeTickFlowProvider, TickFlowProvider


class FakeResponse:
    def __init__(self, payload: object, status_code: int = 200) -> None:
        self.payload = payload
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                "boom",
                request=httpx.Request("POST", "https://api.test"),
                response=httpx.Response(self.status_code),
            )

    def json(self) -> object:
        return self.payload


class FakeClient:
    def __init__(self, response: FakeResponse | None = None, error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.last_request: dict[str, object] = {}
        self.closed = False

    def post(self, url: str, **kwargs: object) -> FakeResponse:
        self.last_request = {"url": url, **kwargs}
        if self.error is not None:
            raise self.error
        assert self.response is not None
        return self.response

    def close(self) -> None:
        self.closed = True


def test_tickflow_provider_maps_batch_quotes() -> None:
    client = FakeClient(
        FakeResponse(
            {
                "data": [
                    {
                        "symbol": "600000.SH",
                        "name": "浦发银行",
                        "last_price": 10.5,
                        "pct_change": 2.3,
                        "turnover": 123000000,
                        "volume": 45600,
                        "time": "2026-05-26T15:00:00+08:00",
                    }
                ]
            }
        )
    )
    provider = TickFlowProvider(
        api_key="tk-test-local",
        base_url="https://api.tickflow.org",
        http_client=client,
    )

    quotes = provider.get_quotes(["600000.SH"])

    assert quotes[0].symbol == "600000.SH"
    assert quotes[0].name == "浦发银行"
    assert quotes[0].pct_change == 2.3
    assert client.last_request["url"] == "https://api.tickflow.org/v1/quotes"
    assert client.last_request["headers"] == {"x-api-key": "tk-test-local"}


def test_tickflow_provider_rejects_missing_key() -> None:
    provider = TickFlowProvider(api_key="", base_url="https://api.tickflow.org")

    with pytest.raises(ProviderFallbackError, match="TICKFLOW_API_KEY"):
        provider.get_quotes(["600000.SH"])


def test_tickflow_provider_sanitizes_request_errors() -> None:
    leaked_key = "tk_secret_leak"
    provider = TickFlowProvider(
        api_key=leaked_key,
        base_url="https://api.tickflow.org",
        http_client=FakeClient(error=RuntimeError(f"boom {leaked_key}")),
    )

    with pytest.raises(ProviderFallbackError) as exc_info:
        provider.get_quotes(["600000.SH"])

    message = str(exc_info.value)
    assert "TickFlow 请求失败" in message
    assert leaked_key not in message


def test_tickflow_fallback_returns_fake_quotes_and_status() -> None:
    provider = FallbackTickFlowProvider(
        primary=TickFlowProvider(api_key="", base_url="https://api.tickflow.org"),
        fallback=FakeTickFlowProvider(),
        fallback_enabled=True,
    )

    quotes, status = provider.get_quotes_with_status(["600000.SH"])

    assert quotes[0].symbol == "600000.SH"
    assert status.provider == "tickflow"
    assert status.status == "fallback"
    assert status.fallback_used is True
    assert status.reason == "TICKFLOW_API_KEY 未配置"
