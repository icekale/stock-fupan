from dataclasses import dataclass

from app.config import Settings
from app.providers.a_stock_data import (
    AStockIndustryRankProvider,
    AStockThsHotProvider,
    EastmoneyGlobalNewsProvider,
)
from app.providers.easy_tdx import EasyTdxMarketDataProvider
from app.providers.llm import FakeLLMProvider, LLMProvider, OpenAILLMProvider
from app.providers.market import (
    FakeMarketDataProvider,
    MarketDataProvider,
)
from app.providers.news import AnspireNewsProvider, FakeNewsProvider, FallbackNewsProvider, NewsProvider
from app.providers.ocr import (
    FakeOcrProvider,
    FallbackOcrProvider,
    OcrProvider,
    OpenAIVisionOcrProvider,
)
from app.providers.review_sources import (
    EastmoneyZtFpProvider,
    ReviewSourceAggregator,
    ThsFupanProvider,
)
from app.providers.runtime_config import RuntimeProviderConfigState
from app.providers.tickflow import (
    FakeTickFlowProvider,
    FallbackTickFlowProvider,
    TickFlowMarketDataProvider,
    TickFlowProvider,
    TickFlowQuoteProvider,
)


@dataclass(frozen=True)
class ProviderBundle:
    market_provider: MarketDataProvider
    news_provider: NewsProvider
    llm_provider: LLMProvider
    ocr_provider: OcrProvider
    tickflow_provider: TickFlowQuoteProvider
    review_source_provider: ReviewSourceAggregator | None = None

    def close(self) -> None:
        _close_provider(self.market_provider)
        _close_provider(self.news_provider)
        _close_provider(self.llm_provider)
        _close_provider(self.ocr_provider)
        _close_provider(self.tickflow_provider)
        if self.review_source_provider is not None:
            _close_provider(self.review_source_provider)

    def __enter__(self) -> "ProviderBundle":
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        self.close()


def create_provider_bundle(
    settings: Settings,
    runtime_config: RuntimeProviderConfigState | None = None,
) -> ProviderBundle:
    _validate_production_providers(settings, runtime_config)
    return ProviderBundle(
        market_provider=_create_market_provider(settings, runtime_config),
        news_provider=_create_news_provider(settings, runtime_config),
        llm_provider=_create_llm_provider(settings),
        ocr_provider=_create_ocr_provider(settings),
        tickflow_provider=_create_tickflow_provider(settings),
        review_source_provider=_create_review_source_provider(settings, runtime_config),
    )


def _runtime_value(
    runtime_config: RuntimeProviderConfigState | None,
    name: str,
    fallback: object,
) -> object:
    if runtime_config is None:
        return fallback
    return getattr(runtime_config, name)


def _create_market_provider(
    settings: Settings,
    runtime_config: RuntimeProviderConfigState | None = None,
) -> MarketDataProvider:
    market_provider = str(_runtime_value(runtime_config, "market_provider", settings.market_provider))
    if market_provider == "fake":
        return FakeMarketDataProvider()
    if market_provider == "tickflow":
        return TickFlowMarketDataProvider(
            api_key=settings.tickflow_api_key,
            base_url=settings.tickflow_base_url,
            timeout_seconds=settings.provider_timeout_seconds,
        )
    if market_provider == "easy_tdx":
        return EasyTdxMarketDataProvider(
            timeout_seconds=settings.provider_timeout_seconds,
        )
    raise ValueError(f"Unsupported MARKET_PROVIDER: {market_provider}")


def _create_news_provider(
    settings: Settings,
    runtime_config: RuntimeProviderConfigState | None = None,
) -> NewsProvider:
    news_provider = str(_runtime_value(runtime_config, "news_provider", settings.news_provider))
    fallback_enabled = bool(
        _runtime_value(runtime_config, "fallback_enabled", settings.provider_fallback_enabled)
    )
    if news_provider == "fake":
        return FakeNewsProvider()
    if news_provider == "anspire":
        return FallbackNewsProvider(
            primary=AnspireNewsProvider(
                api_key=settings.anspire_api_key,
                base_url=settings.anspire_base_url,
                top_k=settings.news_top_k,
                lookback_hours=settings.news_lookback_hours,
                timeout_seconds=settings.provider_timeout_seconds,
            ),
            fallback=FakeNewsProvider(),
            fallback_enabled=fallback_enabled,
        )
    if news_provider == "eastmoney_global":
        return FallbackNewsProvider(
            primary=EastmoneyGlobalNewsProvider(
                timeout_seconds=settings.provider_timeout_seconds,
            ),
            fallback=FakeNewsProvider(),
            fallback_enabled=fallback_enabled,
        )
    raise ValueError(f"Unsupported NEWS_PROVIDER: {news_provider}")


def _create_llm_provider(settings: Settings) -> LLMProvider:
    if settings.llm_provider == "fake":
        return FakeLLMProvider()
    if settings.llm_provider == "openai":
        return OpenAILLMProvider(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            model_name=settings.llm_model,
        )
    raise ValueError(f"Unsupported LLM_PROVIDER: {settings.llm_provider}")


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


def _create_tickflow_provider(settings: Settings) -> TickFlowQuoteProvider:
    if settings.tickflow_provider == "fake":
        return FakeTickFlowProvider()
    if settings.tickflow_provider == "tickflow":
        return FallbackTickFlowProvider(
            primary=TickFlowProvider(
                api_key=settings.tickflow_api_key,
                base_url=settings.tickflow_base_url,
                timeout_seconds=settings.provider_timeout_seconds,
            ),
            fallback=FakeTickFlowProvider(),
            fallback_enabled=settings.provider_fallback_enabled,
        )
    raise ValueError(f"Unsupported TICKFLOW_PROVIDER: {settings.tickflow_provider}")


def _create_review_source_provider(
    settings: Settings,
    runtime_config: RuntimeProviderConfigState | None = None,
) -> ReviewSourceAggregator | None:
    if runtime_config is None:
        if not settings.review_sources_enabled:
            return None
        review_sources = ["ths_fupan", "eastmoney_ztfp"]
    else:
        review_sources = runtime_config.review_sources

    providers: list[object] = []
    if "ths_fupan" in review_sources:
        providers.append(
            ThsFupanProvider(
                source_url=settings.ths_fupan_url,
                timeout_seconds=settings.provider_timeout_seconds,
            )
        )
    if "eastmoney_ztfp" in review_sources:
        providers.append(
            EastmoneyZtFpProvider(
                source_url=settings.eastmoney_ztfp_url,
                timeout_seconds=settings.provider_timeout_seconds,
            )
        )
    if "a_stock_ths_hot" in review_sources:
        providers.append(AStockThsHotProvider(timeout_seconds=settings.provider_timeout_seconds))
    if "a_stock_industry_rank" in review_sources:
        providers.append(AStockIndustryRankProvider(timeout_seconds=settings.provider_timeout_seconds))
    return ReviewSourceAggregator(providers=providers) if providers else None


def _close_provider(provider: object) -> None:
    close = getattr(provider, "close", None)
    if callable(close):
        close()
    for child_name in ("primary", "fallback"):
        child = getattr(provider, child_name, None)
        if child is not None:
            _close_provider(child)


def _validate_production_providers(
    settings: Settings,
    runtime_config: RuntimeProviderConfigState | None = None,
) -> None:
    if settings.app_env != "production" or settings.production_allow_fake_providers:
        return
    market_provider = str(_runtime_value(runtime_config, "market_provider", settings.market_provider))
    news_provider = str(_runtime_value(runtime_config, "news_provider", settings.news_provider))
    fallback_enabled = bool(
        _runtime_value(runtime_config, "fallback_enabled", settings.provider_fallback_enabled)
    )
    fake_providers = {
        "MARKET_PROVIDER": market_provider,
        "NEWS_PROVIDER": news_provider,
        "LLM_PROVIDER": settings.llm_provider,
        "OCR_PROVIDER": settings.ocr_provider,
        "TICKFLOW_PROVIDER": settings.tickflow_provider,
    }
    for name, value in fake_providers.items():
        if value == "fake":
            raise ValueError(f"Production cannot use fake provider: {name}")
    if fallback_enabled:
        raise ValueError("Production cannot use fake fallback: PROVIDER_FALLBACK_ENABLED")
    if settings.ocr_fallback_enabled:
        raise ValueError("Production cannot use fake fallback: OCR_FALLBACK_ENABLED")
    if settings.structured_review_fallback_enabled and settings.structured_review_provider == "llm":
        raise ValueError("Production cannot use fake fallback: STRUCTURED_REVIEW_FALLBACK_ENABLED")
