from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    database_url: str = "sqlite:///./data/stock_review.db"
    reports_root: Path = Path("../../reports")
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4.1-mini"
    llm_provider: str = "fake"
    ocr_provider: str = "fake"
    ocr_fallback_enabled: bool = True
    ocr_model: str = "gpt-4.1-mini"
    structured_review_provider: str = "rule"
    structured_review_fallback_enabled: bool = True
    anspire_api_key: str = ""
    anspire_base_url: str = "https://plugin.anspire.cn/api/ntsearch/search"
    market_provider: str = "tickflow"
    news_provider: str = "anspire"
    provider_fallback_enabled: bool = True
    provider_timeout_seconds: float = 12
    news_top_k: int = 10
    news_lookback_hours: int = 36
    tickflow_api_key: str = ""
    tickflow_base_url: str = "https://api.tickflow.org"
    tickflow_provider: str = "tickflow"
    report_watchlist_enabled: bool = False
    production_allow_fake_providers: bool = False
    watchlist_provider: str = "local"
    watchlist_snapshot_root: Path = Path("./data/watchlists")
    report_brand_name: str = ""
    report_brand_footer: str = ""
    report_disclaimer_enabled: bool = True
    review_sources_enabled: bool = True
    akshare_review_source_enabled: bool = True
    ths_fupan_url: str = "https://stock.10jqka.com.cn/fupan/"
    eastmoney_ztfp_url: str = "https://stock.eastmoney.com/a/cztfp.html"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
