from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app


@pytest.fixture(autouse=True)
def isolate_settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    get_settings.cache_clear()
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'evidence.db'}")
    monkeypatch.setenv("MARKET_PROVIDER", "fake")
    monkeypatch.setenv("NEWS_PROVIDER", "fake")
    monkeypatch.setenv("REVIEW_SOURCES_ENABLED", "false")
    yield
    get_settings.cache_clear()


def test_evidence_parse_preview_endpoint() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/evidence/parse-preview",
            json={
                "content": """
                [{
                  "trade_date": "2026-06-01",
                  "source": "证券时报",
                  "title": "煤炭行业今日净流入资金26.55亿元",
                  "url": "https://example.com/stcn/coal",
                  "published_at": "2026-06-01T15:30:00+08:00",
                  "category": "capital_flow",
                  "claim": "煤炭行业今日净流入资金26.55亿元。",
                  "numbers": {"industry": "煤炭", "net_inflow_yi": 26.55},
                  "confidence": "high",
                  "status": "verified"
                }]
                """
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["valid_count"] == 1
    assert payload["invalid_count"] == 0


def test_evidence_save_and_query_endpoints() -> None:
    item = {
        "trade_date": "2026-06-01",
        "source": "新浪财经",
        "title": "宇树科技科创板IPO过会",
        "url": "https://example.com/sina/unitree",
        "published_at": "2026-06-01T18:00:00+08:00",
        "category": "catalyst",
        "claim": "宇树科技科创板IPO过会。",
        "related_sectors": ["机器人"],
        "confidence": "high",
        "status": "verified",
    }
    with TestClient(app) as client:
        save_response = client.post("/api/evidence", json={"items": [item]})
        list_response = client.get("/api/evidence?trade_date=2026-06-01&status=verified")

    assert save_response.status_code == 200
    assert save_response.json()["items"][0]["id"].startswith("ev_20260601_")
    assert list_response.status_code == 200
    assert list_response.json()["items"][0]["source"] == "新浪财经"


def test_evidence_query_rejects_invalid_status() -> None:
    with TestClient(app) as client:
        response = client.get("/api/evidence?trade_date=2026-06-01&status=bad")

    assert response.status_code == 422


def test_evidence_save_rejects_invalid_verified_capital_flow_without_numeric_numbers() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/evidence",
            json={
                "items": [
                    {
                        "trade_date": "2026-06-01",
                        "source": "证券时报",
                        "title": "行业资金",
                        "url": "https://example.com/fund",
                        "published_at": "2026-06-01T18:00:00+08:00",
                        "category": "capital_flow",
                        "claim": "煤炭净流入。",
                        "numbers": {"industry": "煤炭", "direction": "净流入"},
                        "confidence": "high",
                        "status": "verified",
                    }
                ]
            },
        )

    assert response.status_code == 422
    assert "capital_flow high evidence requires numeric numbers" in response.text


def test_evidence_anspire_candidates_uses_news_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeSearchProvider:
        def search_news_with_status(self, query: str, trade_date: str):
            from app.providers.market import ProviderStatus
            from app.providers.news import NewsSearchResult
            from app.schemas.report import NewsItem

            return NewsSearchResult(
                query=query,
                items=[
                    NewsItem(
                        title="主力资金连续6天净流出",
                        url="https://example.com/jrj/outflow",
                        source="金融界",
                        summary="主力资金连续6天净流出。",
                        published_at="2026-06-01T18:00:00+08:00",
                    )
                ],
                status=ProviderStatus(
                    provider="anspire",
                    status="success",
                    fallback_used=False,
                    reason=None,
                ),
            )

    class FakeBundle:
        news_provider = FakeSearchProvider()

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return None

    monkeypatch.setattr("app.main.create_provider_bundle", lambda settings, runtime_config=None: FakeBundle())

    with TestClient(app) as client:
        response = client.post(
            "/api/evidence/anspire-candidates",
            json={"trade_date": "2026-06-01", "task": "jrj_continuous_outflow"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider_status"]["status"] == "success"
    assert payload["items"][0]["item"]["status"] == "candidate"
