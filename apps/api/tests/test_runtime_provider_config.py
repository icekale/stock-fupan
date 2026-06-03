from sqlalchemy import create_engine, text

from app.config import Settings
from app.db.models import Base
from app.db.session import session_scope
from app.providers.runtime_config import (
    RuntimeProviderConfigInput,
    build_data_source_options_payload,
    get_runtime_provider_config,
    save_runtime_provider_config,
)


def _engine():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    return engine


def test_runtime_config_defaults_from_settings_when_empty() -> None:
    engine = _engine()
    settings = Settings(
        market_provider="tickflow",
        news_provider="anspire",
        review_sources_enabled=True,
        thsdk_enabled=True,
        provider_fallback_enabled=False,
    )

    config = get_runtime_provider_config(engine, settings)

    assert config.market_provider == "tickflow"
    assert config.news_provider == "anspire"
    assert config.review_sources == ["ths_fupan", "eastmoney_ztfp", "thsdk"]
    assert config.fallback_enabled is False
    assert config.updated_at is None


def test_runtime_config_save_and_read_back() -> None:
    engine = _engine()
    settings = Settings()

    saved = save_runtime_provider_config(
        engine,
        RuntimeProviderConfigInput(
            market_provider="tickflow",
            news_provider="eastmoney_global",
            review_sources=["a_stock_ths_hot", "ths_fupan", "a_stock_ths_hot"],
            fallback_enabled=True,
        ),
    )
    loaded = get_runtime_provider_config(engine, settings)

    assert saved.news_provider == "eastmoney_global"
    assert loaded.market_provider == "tickflow"
    assert loaded.news_provider == "eastmoney_global"
    assert loaded.review_sources == ["a_stock_ths_hot", "ths_fupan"]
    assert loaded.fallback_enabled is True
    assert loaded.updated_at is not None


def test_runtime_config_rejects_unknown_provider() -> None:
    engine = _engine()

    try:
        save_runtime_provider_config(
            engine,
            RuntimeProviderConfigInput(
                market_provider="tickflow",
                news_provider="unknown",
                review_sources=[],
                fallback_enabled=True,
            ),
        )
    except ValueError as exc:
        assert "Unsupported NEWS_PROVIDER" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_runtime_config_replaces_singleton_row() -> None:
    engine = _engine()
    settings = Settings()

    save_runtime_provider_config(
        engine,
        RuntimeProviderConfigInput(
            market_provider="tickflow",
            news_provider="fake",
            review_sources=["ths_fupan"],
            fallback_enabled=True,
        ),
    )
    save_runtime_provider_config(
        engine,
        RuntimeProviderConfigInput(
            market_provider="fake",
            news_provider="eastmoney_global",
            review_sources=["a_stock_industry_rank"],
            fallback_enabled=False,
        ),
    )

    loaded = get_runtime_provider_config(engine, settings)
    with session_scope(engine) as session:
        rows = session.execute(text("select count(*) from runtime_provider_config")).scalar()

    assert rows == 1
    assert loaded.market_provider == "fake"
    assert loaded.news_provider == "eastmoney_global"
    assert loaded.review_sources == ["a_stock_industry_rank"]
    assert loaded.fallback_enabled is False


def test_runtime_config_accepts_dragon_tiger_review_source() -> None:
    engine = _engine()
    settings = Settings()

    saved = save_runtime_provider_config(
        engine,
        RuntimeProviderConfigInput(
            market_provider="tickflow",
            news_provider="anspire",
            review_sources=["a_stock_dragon_tiger"],
            fallback_enabled=False,
        ),
    )
    payload = build_data_source_options_payload(saved, settings)
    review_category = next(
        category for category in payload["categories"] if category["key"] == "review_sources"
    )
    dragon_option = next(
        option for option in review_category["options"] if option["key"] == "a_stock_dragon_tiger"
    )

    assert saved.review_sources == ["a_stock_dragon_tiger"]
    assert dragon_option["label"] == "a-stock 东财龙虎榜"
    assert dragon_option["role"] == "增强源 · 龙虎榜情绪资金"
    assert dragon_option["enabled"] is True
