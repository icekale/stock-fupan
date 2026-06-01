from sqlalchemy import create_engine

from app.db.models import Base
from app.schemas.evidence import EvidenceCategory, EvidenceConfidence, EvidenceStatus
from app.services.evidence_service import (
    EvidenceStore,
    parse_evidence_preview,
    validate_evidence_item,
)


def _engine():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    return engine


def test_parse_json_array_preview_valid_item() -> None:
    preview = parse_evidence_preview(
        """
        [
          {
            "trade_date": "2026-06-01",
            "source": "证券时报",
            "title": "煤炭行业今日净流入资金26.55亿元",
            "url": "https://example.com/stcn/coal",
            "published_at": "2026-06-01T15:30:00+08:00",
            "category": "capital_flow",
            "claim": "煤炭行业今日净流入资金26.55亿元。",
            "numbers": {"industry": "煤炭", "net_inflow_yi": 26.55},
            "related_sectors": ["煤炭"],
            "confidence": "high",
            "status": "verified"
          }
        ]
        """
    )

    assert preview.valid_count == 1
    assert preview.invalid_count == 0
    assert preview.items[0].item is not None
    assert preview.items[0].item.source == "证券时报"
    assert preview.items[0].item.category == EvidenceCategory.CAPITAL_FLOW
    assert preview.items[0].item.confidence == EvidenceConfidence.HIGH


def test_parse_table_text_preview() -> None:
    preview = parse_evidence_preview(
        "\t".join(
            [
                "trade_date",
                "source",
                "title",
                "url",
                "published_at",
                "category",
                "claim",
                "confidence",
                "related_sectors",
            ]
        )
        + "\n"
        + "\t".join(
            [
                "2026-06-01",
                "36氪",
                "全球首个Agent原生电脑问世",
                "https://example.com/36kr/pc",
                "2026-06-01T12:00:00+08:00",
                "catalyst",
                "英伟达与微软推动Agent原生电脑方向。",
                "medium",
                "AI PC,AI应用",
            ]
        )
    )

    assert preview.valid_count == 1
    assert preview.items[0].item is not None
    assert preview.items[0].item.related_sectors == ["AI PC", "AI应用"]


def test_high_capital_flow_without_numbers_is_invalid() -> None:
    preview = parse_evidence_preview(
        """
        [{
          "trade_date": "2026-06-01",
          "source": "证券时报",
          "title": "行业资金流向",
          "url": "https://example.com/fund",
          "published_at": "2026-06-01T18:00:00+08:00",
          "category": "capital_flow",
          "claim": "煤炭行业净流入。",
          "confidence": "high",
          "status": "verified"
        }]
        """
    )

    assert preview.valid_count == 0
    assert preview.invalid_count == 1
    assert "capital_flow high evidence requires numbers" in preview.items[0].errors


def test_high_evidence_requires_trade_date_or_previous_day() -> None:
    preview = parse_evidence_preview(
        """
        [{
          "trade_date": "2026-06-01",
          "source": "新浪财经",
          "title": "宇树科技科创板IPO过会",
          "url": "https://example.com/sina/unitree",
          "published_at": "2026-05-28T18:00:00+08:00",
          "category": "catalyst",
          "claim": "宇树科技科创板IPO过会。",
          "confidence": "high",
          "status": "verified"
        }]
        """
    )

    assert preview.valid_count == 0
    assert "high evidence requires trade date or previous-day date match" in preview.items[0].errors


def test_store_saves_and_lists_verified_evidence() -> None:
    engine = _engine()
    preview = parse_evidence_preview(
        """
        [{
          "trade_date": "2026-06-01",
          "source": "金融界",
          "title": "主力资金连续6天净流出",
          "url": "https://example.com/jrj/outflow",
          "published_at": "2026-06-01T18:00:00+08:00",
          "category": "risk",
          "claim": "主力资金连续6天净流出。",
          "numbers": {"continuous_outflow_days": 6},
          "related_sectors": ["全市场"],
          "confidence": "high",
          "status": "verified"
        }]
        """
    )
    item = preview.items[0].item
    assert item is not None

    store = EvidenceStore(engine)
    saved = store.save_items([item])
    loaded = store.list_items("2026-06-01", status=EvidenceStatus.VERIFIED)

    assert len(saved) == 1
    assert saved[0].id.startswith("ev_20260601_")
    assert len(loaded) == 1
    assert loaded[0].claim == "主力资金连续6天净流出。"


def test_validate_evidence_item_is_importable() -> None:
    assert callable(validate_evidence_item)
