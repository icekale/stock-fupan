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
            "minute_kline": "missing_key",
            "last_error": "TICKFLOW_API_KEY 未配置",
        }
    return {
        "configured": True,
        "status": "ready",
        "base_url": normalized_base_url,
        "timeout_seconds": timeout_seconds,
        "minute_kline": "not_checked",
        "last_error": None,
    }
