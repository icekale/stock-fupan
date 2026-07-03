from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    database_url: str = "sqlite:///./data/stock_review.db"
    reports_root: Path = Path("../../reports")
    cors_allow_origins: str = (
        "http://localhost:3000,http://127.0.0.1:3000,http://192.168.5.28:3000"
    )
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
    market_provider: str = "a_stock"
    news_provider: str = "anspire"
    provider_fallback_enabled: bool = True
    provider_timeout_seconds: float = 12
    news_top_k: int = 10
    news_lookback_hours: int = 36
    tickflow_api_key: str = ""
    tickflow_base_url: str = "https://api.tickflow.org"
    tickflow_provider: str = "tickflow"
    watchlist_alert_schedule_enabled: bool = False
    watchlist_alert_morning_time: str = "10:00"
    watchlist_alert_afternoon_time: str = "14:30"
    watchlist_alert_review_time: str = "19:30"
    watchlist_alert_timezone: str = "Asia/Shanghai"
    watchlist_alert_daily_limit: int = 5
    watchlist_alert_review_limit: int = 10
    watchlist_alert_stale_days: int = 4
    watchlist_alert_muted_days: int = 3
    watchlist_alert_opportunity_min_score: int = 70
    wecom_webhook_url: str = ""
    feishu_webhook_url: str = ""
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_to: str = ""
    report_watchlist_enabled: bool = False
    production_allow_fake_providers: bool = False
    watchlist_provider: str = "local"
    watchlist_snapshot_root: Path = Path("./data/watchlists")
    report_brand_name: str = ""
    report_brand_footer: str = ""
    report_disclaimer_enabled: bool = True
    review_sources_enabled: bool = True
    ths_fupan_url: str = "https://stock.10jqka.com.cn/fupan/"
    eastmoney_ztfp_url: str = "https://stock.eastmoney.com/a/cztfp.html"
    thsdk_enabled: bool = False
    previous_review_html_path: Path | None = None
    report_schedule_enabled: bool = False
    report_schedule_close_time: str = "19:00"
    report_schedule_timezone: str = "Asia/Shanghai"
    morning_auction_free_stockdb_base_url: str = "http://192.168.5.221:7899"
    morning_auction_model_path: Path = Path(
        "./artifacts/morning_auction/free_stockdb_lgbm_20210703_20260703_l120_t1close.pkl"
    )
    morning_auction_metadata_path: Path = Path(
        "./artifacts/morning_auction/free_stockdb_lgbm_20210703_20260703_l120_t1close.metadata.json"
    )
    morning_auction_trial_log_path: Path = Path("./data/morning_auction/trial_log.json")
    morning_auction_lookback: int = 120
    morning_auction_top_n: int = 3
    morning_auction_max_items: int = 50
    morning_auction_timeout_seconds: float = 180

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
