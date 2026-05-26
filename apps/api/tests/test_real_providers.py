from app.providers.market import ProviderStatus
from app.providers.news import SectorNewsResult
from app.schemas.report import NewsItem


def test_provider_status_serializes_for_snapshot() -> None:
    status = ProviderStatus(
        provider="akshare",
        status="fallback",
        fallback_used=True,
        reason="AkShare v0.2 暂不支持历史日期",
    )

    assert status.model_dump(mode="json") == {
        "provider": "akshare",
        "status": "fallback",
        "fallback_used": True,
        "reason": "AkShare v0.2 暂不支持历史日期",
    }


def test_sector_news_result_keeps_sector_status_and_items() -> None:
    item = NewsItem(
        title="机器人产业链催化增强",
        url="https://example.com/news",
        source="示例财经",
        summary="机器人方向出现政策和产业消息共振。",
        matched_sector="机器人",
        weight=0.8,
    )
    result = SectorNewsResult(
        sector="机器人",
        items=[item],
        status=ProviderStatus(
            provider="anspire",
            status="success",
            fallback_used=False,
            reason=None,
        ),
    )

    assert result.sector == "机器人"
    assert result.items == [item]
    assert result.status.provider == "anspire"
    assert result.status.status == "success"
