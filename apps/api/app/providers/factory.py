from dataclasses import dataclass

from app.config import Settings
from app.providers.llm import FakeLLMProvider, LLMProvider
from app.providers.market import (
    AkShareMarketDataProvider,
    FakeMarketDataProvider,
    FallbackMarketDataProvider,
    MarketDataProvider,
)
from app.providers.news import AnspireNewsProvider, FakeNewsProvider, FallbackNewsProvider, NewsProvider


@dataclass(frozen=True)
class ProviderBundle:
    market_provider: MarketDataProvider
    news_provider: NewsProvider
    llm_provider: LLMProvider


def create_provider_bundle(settings: Settings) -> ProviderBundle:
    return ProviderBundle(
        market_provider=_create_market_provider(settings),
        news_provider=_create_news_provider(settings),
        llm_provider=FakeLLMProvider(),
    )


def _create_market_provider(settings: Settings) -> MarketDataProvider:
    if settings.market_provider == "fake":
        return FakeMarketDataProvider()
    if settings.market_provider == "akshare":
        return FallbackMarketDataProvider(
            primary=AkShareMarketDataProvider(),
            fallback=FakeMarketDataProvider(),
            fallback_enabled=settings.provider_fallback_enabled,
        )
    raise ValueError(f"Unsupported MARKET_PROVIDER: {settings.market_provider}")


def _create_news_provider(settings: Settings) -> NewsProvider:
    if settings.news_provider == "fake":
        return FakeNewsProvider()
    if settings.news_provider == "anspire":
        return FallbackNewsProvider(
            primary=AnspireNewsProvider(
                api_key=settings.anspire_api_key,
                base_url=settings.anspire_base_url,
                top_k=settings.news_top_k,
                lookback_hours=settings.news_lookback_hours,
                timeout_seconds=settings.provider_timeout_seconds,
            ),
            fallback=FakeNewsProvider(),
            fallback_enabled=settings.provider_fallback_enabled,
        )
    raise ValueError(f"Unsupported NEWS_PROVIDER: {settings.news_provider}")
