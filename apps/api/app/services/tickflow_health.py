def check_tickflow_health(
    api_key: str,
    base_url: str,
    timeout_seconds: float,
) -> dict[str, object]:
    normalized_base_url = base_url.rstrip("/")
    if not api_key:
        return {
            "configured": False,
            "status": "disabled",
            "base_url": normalized_base_url,
            "timeout_seconds": timeout_seconds,
            "realtime": "missing_key",
            "daily_kline": "missing_key",
            "minute_kline": "missing_key",
            "latency_ms": None,
            "last_error": "TICKFLOW_API_KEY 未配置",
            "fallback_source": "local",
        }
    return {
        "configured": True,
        "status": "ready",
        "base_url": normalized_base_url,
        "timeout_seconds": timeout_seconds,
        "realtime": "not_checked",
        "daily_kline": "not_checked",
        "minute_kline": "not_checked",
        "latency_ms": None,
        "last_error": None,
        "fallback_source": None,
    }
