from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from pydantic import BaseModel
from sqlalchemy import Engine, select

from app.config import Settings
from app.db.models import RuntimeProviderConfig
from app.db.session import session_scope


MarketProviderKey = Literal["tickflow", "easy_tdx", "fake"]
NewsProviderKey = Literal["anspire", "eastmoney_global", "fake"]
ReviewSourceKey = Literal[
    "ths_fupan",
    "eastmoney_ztfp",
    "a_stock_ths_hot",
    "a_stock_industry_rank",
]

MARKET_PROVIDER_KEYS = {"tickflow", "easy_tdx", "fake"}
NEWS_PROVIDER_KEYS = {"anspire", "eastmoney_global", "fake"}
REVIEW_SOURCE_KEYS = {
    "ths_fupan",
    "eastmoney_ztfp",
    "a_stock_ths_hot",
    "a_stock_industry_rank",
}


class RuntimeProviderConfigInput(BaseModel):
    market_provider: str
    news_provider: str
    review_sources: list[str]
    fallback_enabled: bool


@dataclass(frozen=True)
class RuntimeProviderConfigState:
    market_provider: str
    news_provider: str
    review_sources: list[str]
    fallback_enabled: bool
    updated_at: datetime | None = None


def get_runtime_provider_config(engine: Engine, settings: Settings) -> RuntimeProviderConfigState:
    with session_scope(engine) as session:
        row = session.scalars(
            select(RuntimeProviderConfig).order_by(RuntimeProviderConfig.id.asc())
        ).first()
        if row is None:
            return default_runtime_provider_config(settings)
        return RuntimeProviderConfigState(
            market_provider=row.market_provider,
            news_provider=row.news_provider,
            review_sources=list(row.review_sources or []),
            fallback_enabled=bool(row.fallback_enabled),
            updated_at=row.updated_at,
        )


def default_runtime_provider_config(settings: Settings) -> RuntimeProviderConfigState:
    review_sources: list[str] = []
    if settings.review_sources_enabled:
        review_sources.extend(["ths_fupan", "eastmoney_ztfp"])
    return RuntimeProviderConfigState(
        market_provider=settings.market_provider,
        news_provider=settings.news_provider,
        review_sources=_dedupe_review_sources(review_sources),
        fallback_enabled=settings.provider_fallback_enabled,
        updated_at=None,
    )


def save_runtime_provider_config(
    engine: Engine,
    payload: RuntimeProviderConfigInput,
) -> RuntimeProviderConfigState:
    _validate_runtime_config(payload)
    review_sources = _dedupe_review_sources(payload.review_sources)
    with session_scope(engine) as session:
        existing = session.scalars(
            select(RuntimeProviderConfig).order_by(RuntimeProviderConfig.id.asc())
        ).first()
        if existing is None:
            existing = RuntimeProviderConfig(
                market_provider=payload.market_provider,
                news_provider=payload.news_provider,
                review_sources=review_sources,
                fallback_enabled=payload.fallback_enabled,
            )
            session.add(existing)
        else:
            existing.market_provider = payload.market_provider
            existing.news_provider = payload.news_provider
            existing.review_sources = review_sources
            existing.fallback_enabled = payload.fallback_enabled
        session.flush()
        return RuntimeProviderConfigState(
            market_provider=existing.market_provider,
            news_provider=existing.news_provider,
            review_sources=list(existing.review_sources or []),
            fallback_enabled=bool(existing.fallback_enabled),
            updated_at=existing.updated_at,
        )


def _validate_runtime_config(payload: RuntimeProviderConfigInput) -> None:
    if payload.market_provider not in MARKET_PROVIDER_KEYS:
        raise ValueError(f"Unsupported MARKET_PROVIDER: {payload.market_provider}")
    if payload.news_provider not in NEWS_PROVIDER_KEYS:
        raise ValueError(f"Unsupported NEWS_PROVIDER: {payload.news_provider}")
    unsupported = [source for source in payload.review_sources if source not in REVIEW_SOURCE_KEYS]
    if unsupported:
        raise ValueError(f"Unsupported REVIEW_SOURCE: {unsupported[0]}")


def _dedupe_review_sources(values: list[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        output.append(value)
    return output


@dataclass(frozen=True)
class ProviderOption:
    key: str
    category: str
    label: str
    role: str
    requires_key: bool = False
    env_key_name: str | None = None
    experimental: bool = False
    local: bool = False


PROVIDER_OPTIONS: tuple[ProviderOption, ...] = (
    ProviderOption("tickflow", "market_provider", "TickFlow", "主源 · 行情", True, "tickflow_api_key"),
    ProviderOption("easy_tdx", "market_provider", "Easy TDX", "公开源 · 通达信行情"),
    ProviderOption("fake", "market_provider", "Fake", "本地 · 行情占位", False, None, False, True),
    ProviderOption("anspire", "news_provider", "Anspire", "主源 · 新闻", True, "anspire_api_key"),
    ProviderOption("eastmoney_global", "news_provider", "东财全球资讯", "增强源 · 7x24 新闻"),
    ProviderOption("fake", "news_provider", "Fake", "本地 · 新闻占位", False, None, False, True),
    ProviderOption("ths_fupan", "review_sources", "同花顺复盘", "辅助源 · 题材复盘"),
    ProviderOption("eastmoney_ztfp", "review_sources", "东方财富涨停复盘", "辅助源 · 涨停质量"),
    ProviderOption("a_stock_ths_hot", "review_sources", "a-stock 同花顺热点", "增强源 · 强势股归因"),
    ProviderOption("a_stock_industry_rank", "review_sources", "a-stock 东财行业排名", "增强源 · 行业轮动"),
)


def build_data_source_options_payload(
    config: RuntimeProviderConfigState,
    settings: Settings,
) -> dict[str, object]:
    return {
        "current": {
            "market_provider": config.market_provider,
            "news_provider": config.news_provider,
            "review_sources": config.review_sources,
            "fallback_enabled": config.fallback_enabled,
            "updated_at": config.updated_at.isoformat() if config.updated_at else None,
        },
        "categories": [
            _category_payload("market_provider", "行情源", "single", config, settings),
            _category_payload("news_provider", "新闻源", "single", config, settings),
            _category_payload("review_sources", "复盘辅助源", "multiple", config, settings),
        ],
    }


def config_status_items(config: RuntimeProviderConfigState, settings: Settings) -> list[dict[str, object]]:
    selected_keys = {
        "market_provider": {config.market_provider},
        "news_provider": {config.news_provider},
        "review_sources": set(config.review_sources),
    }
    items: list[dict[str, object]] = []
    for option in PROVIDER_OPTIONS:
        enabled = option.key in selected_keys[option.category]
        items.append(
            {
                "name": option.label,
                "role": option.role,
                "configured": _option_configured(option, settings),
                "enabled": enabled,
                "status": _option_status(option, settings, enabled),
                "detail": _option_detail(option, settings, enabled),
            }
        )
    return items


def _category_payload(
    key: str,
    label: str,
    selection: str,
    config: RuntimeProviderConfigState,
    settings: Settings,
) -> dict[str, object]:
    current_values = set(config.review_sources) if key == "review_sources" else {
        getattr(config, key)
    }
    return {
        "key": key,
        "label": label,
        "selection": selection,
        "options": [
            {
                "key": option.key,
                "label": option.label,
                "role": option.role,
                "configured": _option_configured(option, settings),
                "enabled": option.key in current_values,
                "status": _option_choice_status(option, settings),
                "requires_key": option.requires_key,
                "experimental": option.experimental,
                "detail": _option_choice_detail(option, settings),
            }
            for option in PROVIDER_OPTIONS
            if option.category == key
        ],
    }


def _option_configured(option: ProviderOption, settings: Settings) -> bool:
    if not option.requires_key:
        return True
    value = getattr(settings, option.env_key_name or "", "")
    return bool(value)


def _option_status(option: ProviderOption, settings: Settings, enabled: bool) -> str:
    if option.experimental and enabled:
        return "experimental"
    if not enabled:
        return "disabled"
    if option.local:
        return "local"
    if not _option_configured(option, settings):
        return "missing_key"
    return "ready"


def _option_choice_status(option: ProviderOption, settings: Settings) -> str:
    if option.experimental:
        return "experimental"
    if option.local:
        return "local"
    if not _option_configured(option, settings):
        return "missing_key"
    return "ready"


def _option_detail(option: ProviderOption, settings: Settings, enabled: bool) -> str:
    if not enabled:
        return "未启用"
    if option.requires_key:
        configured = _option_configured(option, settings)
        return f"{option.env_key_name.upper()}={'已配置' if configured else '未配置'}"
    return "已启用"


def _option_choice_detail(option: ProviderOption, settings: Settings) -> str:
    if option.requires_key:
        configured = _option_configured(option, settings)
        return f"需要 {option.env_key_name.upper()}，当前{'已配置' if configured else '未配置'}"
    if option.local:
        return "本地占位数据，仅用于开发或故障回退"
    return "无需 API Key，使用公开数据接口"
