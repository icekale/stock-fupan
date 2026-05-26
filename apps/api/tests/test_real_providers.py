import pytest

from app.providers.market import (
    FakeMarketDataProvider,
    FallbackMarketDataProvider,
    MarketCloseSnapshot,
    ProviderFallbackError,
)
from app.providers.market import ProviderStatus
from app.providers.news import FakeNewsProvider, FallbackNewsProvider, SectorNewsResult
from app.schemas.report import NewsItem


def test_provider_status_serializes_for_snapshot() -> None:
    status = ProviderStatus(
        provider="akshare",
        status="fallback",
        fallback_used=True,
        reason="AkShare v0.2 暂不支持历史日期",
    )

    assert status.model_dump(mode="json") == {
        "provider": "akshare",
        "status": "fallback",
        "fallback_used": True,
        "reason": "AkShare v0.2 暂不支持历史日期",
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
    provider_name = "akshare"

    def get_close_snapshot(self, trade_date: str) -> MarketCloseSnapshot:
        raise ProviderFallbackError("AkShare v0.2 暂不支持历史日期")


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
    assert status.provider == "akshare"
    assert status.status == "fallback"
    assert status.fallback_used is True
    assert status.reason == "AkShare v0.2 暂不支持历史日期"


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
