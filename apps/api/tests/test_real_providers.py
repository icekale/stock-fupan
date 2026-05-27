import pytest

from app.config import Settings
from app.providers.factory import create_provider_bundle
from app.providers.llm import OpenAILLMProvider
from app.providers.market import (
    FakeMarketDataProvider,
    FallbackMarketDataProvider,
    MarketCloseSnapshot,
    ProviderFallbackError,
)
from app.providers.market import ProviderStatus
from app.providers.news import AnspireNewsProvider, FakeNewsProvider, FallbackNewsProvider, SectorNewsResult
from app.providers.tickflow import FallbackTickFlowProvider
from app.providers.tickflow import TickFlowMarketDataProvider
from app.schemas.report import NewsItem


def test_provider_status_serializes_for_snapshot() -> None:
    status = ProviderStatus(
        provider="tickflow",
        status="fallback",
        fallback_used=True,
        reason="TickFlow 行情数据不足",
    )

    assert status.model_dump(mode="json") == {
        "provider": "tickflow",
        "status": "fallback",
        "fallback_used": True,
        "reason": "TickFlow 行情数据不足",
    }


def test_sector_news_result_keeps_sector_status_and_items() -> None:
    item = NewsItem(
        title="机器人产业链催化增强",
        url="https://example.com/news",
        source="示例财经",
        summary="机器人方向出现政策和产业消息共振。",
        matched_sector="机器人",
        weight=0.8,
    )
    result = SectorNewsResult(
        sector="机器人",
        items=[item],
        status=ProviderStatus(
            provider="anspire",
            status="success",
            fallback_used=False,
            reason=None,
        ),
    )

    assert result.sector == "机器人"
    assert result.items == [item]
    assert result.status.provider == "anspire"
    assert result.status.status == "success"


class BrokenMarketProvider:
    provider_name = "tickflow"

    def get_close_snapshot(self, trade_date: str) -> MarketCloseSnapshot:
        raise ProviderFallbackError("TickFlow 行情数据不足")


class BrokenNewsProvider:
    provider_name = "anspire"

    def search_sector_news(self, sector_name: str, trade_date: str) -> list[NewsItem]:
        raise ProviderFallbackError("ANSPIRE_API_KEY 未配置")


def test_market_fallback_returns_fake_snapshot_and_reason() -> None:
    provider = FallbackMarketDataProvider(
        primary=BrokenMarketProvider(),
        fallback=FakeMarketDataProvider(),
        fallback_enabled=True,
    )

    snapshot, status = provider.get_close_snapshot_with_status("2026-05-25")

    assert snapshot.raw_sectors[0].name == "机器人"
    assert status.provider == "tickflow"
    assert status.status == "fallback"
    assert status.fallback_used is True
    assert status.reason == "TickFlow 行情数据不足"


def test_market_fallback_can_raise_when_disabled() -> None:
    provider = FallbackMarketDataProvider(
        primary=BrokenMarketProvider(),
        fallback=FakeMarketDataProvider(),
        fallback_enabled=False,
    )

    with pytest.raises(ProviderFallbackError):
        provider.get_close_snapshot_with_status("2026-05-25")


def test_news_fallback_returns_fake_items_and_reason() -> None:
    provider = FallbackNewsProvider(
        primary=BrokenNewsProvider(),
        fallback=FakeNewsProvider(),
        fallback_enabled=True,
    )

    result = provider.search_sector_news_with_status("机器人", "2026-05-26")

    assert result.items[0].matched_sector == "机器人"
    assert result.status.provider == "anspire"
    assert result.status.status == "fallback"
    assert result.status.fallback_used is True
    assert result.status.reason == "ANSPIRE_API_KEY 未配置"



class FakeResponse:
    def __init__(self, status_code: int, payload: dict[str, object]) -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = str(payload)

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise ProviderFallbackError(f"Anspire HTTP {self.status_code}")

    def json(self) -> dict[str, object]:
        return self._payload


class FakeHttpClient:
    def __init__(self, response: FakeResponse | None = None, error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.last_headers: dict[str, str] = {}
        self.last_params: dict[str, object] = {}
        self.closed = False

    def get(self, _url: str, headers: dict[str, str], params: dict[str, object], timeout: float) -> FakeResponse:
        self.last_headers = headers
        self.last_params = params
        if self.error is not None:
            raise self.error
        if self.response is None:
            raise RuntimeError("missing fake response")
        return self.response

    def close(self) -> None:
        self.closed = True


def test_anspire_provider_maps_results_to_news_items() -> None:
    client = FakeHttpClient(
        FakeResponse(
            200,
            {
                "data": [
                    {
                        "title": "机器人产业链催化增强",
                        "url": "https://example.com/robot",
                        "source": "财联社",
                        "summary": "机器人方向出现政策催化。",
                        "published_at": "2026-05-26T14:30:00+08:00",
                    }
                ]
            },
        )
    )
    provider = AnspireNewsProvider(
        api_key="secret-key",
        base_url="https://plugin.anspire.cn/api/ntsearch/search",
        top_k=5,
        lookback_hours=36,
        http_client=client,
    )

    items = provider.search_sector_news("机器人", "2026-05-26")

    assert client.last_headers["Authorization"] == "Bearer secret-key"
    assert client.last_params["query"] == "机器人 A股"
    assert client.last_params["top_k"] == 5
    assert "search_type" not in client.last_params
    assert items[0].title == "机器人产业链催化增强"
    assert items[0].source == "财联社"
    assert items[0].matched_sector == "机器人"
    assert items[0].weight == 0.9


def test_anspire_provider_rejects_missing_key() -> None:
    provider = AnspireNewsProvider(api_key="")

    with pytest.raises(ProviderFallbackError, match="ANSPIRE_API_KEY"):
        provider.search_sector_news("机器人", "2026-05-26")


def test_anspire_provider_rejects_empty_results() -> None:
    provider = AnspireNewsProvider(
        api_key="secret-key",
        http_client=FakeHttpClient(FakeResponse(200, {"data": []})),
    )

    with pytest.raises(ProviderFallbackError, match="无结果"):
        provider.search_sector_news("机器人", "2026-05-26")


def test_anspire_provider_closes_owned_client(monkeypatch) -> None:
    owned_client = FakeHttpClient()
    monkeypatch.setattr("app.providers.news.httpx.Client", lambda: owned_client)

    provider = AnspireNewsProvider(api_key="secret-key")
    returned = provider.__enter__()

    assert returned is provider
    provider.__exit__(None, None, None)

    assert owned_client.closed is True


def test_anspire_provider_does_not_close_injected_client() -> None:
    injected_client = FakeHttpClient()
    provider = AnspireNewsProvider(api_key="secret-key", http_client=injected_client)

    provider.close()

    assert injected_client.closed is False


def test_anspire_provider_sanitizes_request_failures() -> None:
    leaked_token = "sk-test-secret-token"
    provider = AnspireNewsProvider(
        api_key="secret-key",
        http_client=FakeHttpClient(error=RuntimeError(f"boom Authorization Bearer {leaked_token}")),
    )

    with pytest.raises(ProviderFallbackError) as exc_info:
        provider.search_sector_news("机器人", "2026-05-26")

    message = str(exc_info.value)
    assert "Anspire 请求失败" in message
    assert leaked_token not in message
    assert "secret-key" not in message
    assert "Authorization" not in message


def test_provider_factory_uses_tickflow_market_without_market_fallback() -> None:
    settings = Settings(
        market_provider="tickflow",
        news_provider="anspire",
        provider_fallback_enabled=False,
        anspire_api_key="secret-key",
        tickflow_api_key="tk-test-local",
    )

    bundle = create_provider_bundle(settings)

    assert isinstance(bundle.market_provider, TickFlowMarketDataProvider)
    assert isinstance(bundle.news_provider, FallbackNewsProvider)
    assert isinstance(bundle.news_provider.primary, AnspireNewsProvider)


def test_provider_factory_can_force_fake_providers() -> None:
    settings = Settings(market_provider="fake", news_provider="fake")

    bundle = create_provider_bundle(settings)

    assert isinstance(bundle.market_provider, FakeMarketDataProvider)
    assert isinstance(bundle.news_provider, FakeNewsProvider)


def test_provider_bundle_close_closes_nested_anspire_owned_client(monkeypatch) -> None:
    owned_client = FakeHttpClient()
    monkeypatch.setattr("app.providers.news.httpx.Client", lambda: owned_client)
    settings = Settings(
        market_provider="tickflow",
        news_provider="anspire",
        anspire_api_key="secret-key",
    )

    bundle = create_provider_bundle(settings)
    bundle.close()

    assert owned_client.closed is True


def test_settings_default_to_rule_structured_review() -> None:
    settings = Settings()

    assert settings.llm_provider == "fake"
    assert settings.structured_review_provider == "rule"
    assert settings.structured_review_fallback_enabled is True


def test_settings_defaults_disable_watchlist_and_production_fake_allowance() -> None:
    settings = Settings(_env_file=None)

    assert settings.market_provider == "tickflow"
    assert settings.report_watchlist_enabled is False
    assert settings.production_allow_fake_providers is False


def test_provider_factory_rejects_fake_market_provider_in_production() -> None:
    settings = Settings(app_env="production", market_provider="fake")

    with pytest.raises(ValueError, match="Production cannot use fake provider"):
        create_provider_bundle(settings)


def test_provider_factory_rejects_fake_fallback_in_production() -> None:
    settings = Settings(
        app_env="production",
        market_provider="tickflow",
        news_provider="anspire",
        llm_provider="openai",
        openai_api_key="sk-test-local",
        ocr_provider="openai",
        ocr_fallback_enabled=False,
        tickflow_provider="tickflow",
        anspire_api_key="secret-key",
        tickflow_api_key="tk-test-local",
        provider_fallback_enabled=True,
    )

    with pytest.raises(ValueError, match="Production cannot use fake fallback"):
        create_provider_bundle(settings)


def test_provider_factory_can_create_openai_llm_provider() -> None:
    settings = Settings(
        llm_provider="openai",
        openai_api_key="sk-test-local",
        openai_base_url="https://api.openai.com/v1",
        llm_model="gpt-4.1-mini",
    )

    bundle = create_provider_bundle(settings)

    assert isinstance(bundle.llm_provider, OpenAILLMProvider)
    assert bundle.llm_provider.model_name == "gpt-4.1-mini"


def test_provider_factory_includes_tickflow_provider() -> None:
    settings = Settings(
        tickflow_provider="tickflow",
        tickflow_api_key="tk-test-local",
        tickflow_base_url="https://api.tickflow.org",
    )

    bundle = create_provider_bundle(settings)

    assert isinstance(bundle.tickflow_provider, FallbackTickFlowProvider)
