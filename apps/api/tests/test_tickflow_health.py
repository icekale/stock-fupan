from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import app
from app.services.tickflow_health import check_tickflow_health


def test_tickflow_health_missing_key_is_disabled() -> None:
    result = check_tickflow_health(
        api_key="",
        base_url="https://api.tickflow.org",
        timeout_seconds=12,
    )

    assert result == {
        "configured": False,
        "status": "disabled",
        "base_url": "https://api.tickflow.org",
        "timeout_seconds": 12,
        "realtime": "missing_key",
        "daily_kline": "missing_key",
        "minute_kline": "missing_key",
        "latency_ms": None,
        "last_error": "TICKFLOW_API_KEY 未配置",
        "fallback_source": "local",
    }


def test_tickflow_health_configured_is_ready_without_live_check() -> None:
    result = check_tickflow_health(
        api_key="tk-test-local",
        base_url="https://api.tickflow.org/",
        timeout_seconds=8,
    )

    assert result == {
        "configured": True,
        "status": "ready",
        "base_url": "https://api.tickflow.org",
        "timeout_seconds": 8,
        "realtime": "not_checked",
        "daily_kline": "not_checked",
        "minute_kline": "not_checked",
        "latency_ms": None,
        "last_error": None,
        "fallback_source": None,
    }


def test_tickflow_health_endpoint_uses_settings() -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(
        tickflow_api_key="tk-test-local",
        tickflow_base_url="https://api.example.test/",
        provider_timeout_seconds=3,
    )
    try:
        response = TestClient(app).get("/api/tickflow/health")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "configured": True,
        "status": "ready",
        "base_url": "https://api.example.test",
        "timeout_seconds": 3,
        "realtime": "not_checked",
        "daily_kline": "not_checked",
        "minute_kline": "not_checked",
        "latency_ms": None,
        "last_error": None,
        "fallback_source": None,
    }
