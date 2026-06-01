from sqlalchemy import create_engine

from app.db.models import Base
from app.schemas.evidence import EvidenceCategory, EvidenceConfidence, EvidenceStatus
from app.schemas.report import NewsItem
from app.services.evidence_service import (
    EvidenceStore,
    build_candidate_preview_from_news,
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


def test_parse_comma_table_preserves_extra_related_sectors_columns() -> None:
    preview = parse_evidence_preview(
        ",".join(
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
        + ",".join(
            [
                "2026-06-01",
                "36氪",
                "全球首个Agent原生电脑问世",
                "https://example.com/36kr/pc",
                "2026-06-01T12:00:00+08:00",
                "catalyst",
                "英伟达与微软推动Agent原生电脑方向。",
                "medium",
                "AI PC",
                "AI应用",
            ]
        )
    )

    assert preview.valid_count == 1
    assert preview.items[0].item is not None
    assert preview.items[0].item.related_sectors == ["AI PC", "AI应用"]


def test_parse_json_related_sectors_string_normalizes_to_list() -> None:
    preview = parse_evidence_preview(
        """
        [{
          "trade_date": "2026-06-01",
          "source": "36氪",
          "title": "全球首个Agent原生电脑问世",
          "url": "https://example.com/36kr/pc",
          "published_at": "2026-06-01T12:00:00+08:00",
          "category": "catalyst",
          "claim": "英伟达与微软推动Agent原生电脑方向。",
          "confidence": "medium",
          "related_sectors": "AI PC，AI应用"
        }]
        """
    )

    assert preview.valid_count == 1
    assert preview.items[0].item is not None
    assert preview.items[0].item.related_sectors == ["AI PC", "AI应用"]


def test_blank_trade_date_is_invalid_for_non_high_evidence() -> None:
    preview = parse_evidence_preview(
        """
        [{
          "trade_date": "",
          "source": "36氪",
          "title": "全球首个Agent原生电脑问世",
          "url": "https://example.com/36kr/pc",
          "published_at": "2026-06-01T12:00:00+08:00",
          "category": "catalyst",
          "claim": "英伟达与微软推动Agent原生电脑方向。",
          "confidence": "medium"
        }]
        """
    )

    assert preview.valid_count == 0
    assert preview.invalid_count == 1
    assert "trade_date is required" in preview.items[0].errors


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


def test_high_capital_flow_requires_numeric_numbers_value() -> None:
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
          "numbers": {"note": "净流入明显"},
          "confidence": "high",
          "status": "verified"
        }]
        """
    )

    assert preview.valid_count == 0
    assert preview.invalid_count == 1
    assert "capital_flow high evidence requires numeric numbers" in preview.items[0].errors


def test_confidence_is_required() -> None:
    preview = parse_evidence_preview(
        """
        [{
          "trade_date": "2026-06-01",
          "source": "36氪",
          "title": "全球首个Agent原生电脑问世",
          "url": "https://example.com/36kr/pc",
          "published_at": "2026-06-01T12:00:00+08:00",
          "category": "catalyst",
          "claim": "英伟达与微软推动Agent原生电脑方向。"
        }]
        """
    )

    assert preview.valid_count == 0
    assert preview.invalid_count == 1
    assert "confidence" in preview.items[0].errors[0]


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


def test_store_updates_existing_evidence_by_public_id() -> None:
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
    updated = saved[0].model_copy(
        update={
            "claim": "主力资金连续6天净流出，风险延续。",
            "confidence": EvidenceConfidence.MEDIUM,
        }
    )

    store.save_items([updated])
    loaded = store.list_items("2026-06-01", status=EvidenceStatus.VERIFIED)

    assert len(loaded) == 1
    assert loaded[0].id == saved[0].id
    assert loaded[0].claim == "主力资金连续6天净流出，风险延续。"
    assert loaded[0].confidence == EvidenceConfidence.MEDIUM


def test_store_rejects_duplicate_explicit_ids_in_batch() -> None:
    engine = _engine()
    preview = parse_evidence_preview(
        """
        [
          {
            "id": "ev_20260601_001",
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
          },
          {
            "id": "ev_20260601_001",
            "trade_date": "2026-06-01",
            "source": "金融界",
            "title": "主力资金连续6天净流出更新",
            "url": "https://example.com/jrj/outflow-2",
            "published_at": "2026-06-01T18:05:00+08:00",
            "category": "risk",
            "claim": "主力资金连续6天净流出，风险延续。",
            "numbers": {"continuous_outflow_days": 6},
            "related_sectors": ["全市场"],
            "confidence": "medium",
            "status": "verified"
          }
        ]
        """
    )
    items = [preview_item.item for preview_item in preview.items]
    assert all(item is not None for item in items)

    store = EvidenceStore(engine)
    try:
        store.save_items([item for item in items if item is not None])
    except ValueError as exc:
        assert str(exc) == "duplicate evidence id in batch: ev_20260601_001"
    else:
        raise AssertionError("expected ValueError")


def test_validate_evidence_item_is_importable() -> None:
    assert callable(validate_evidence_item)


def test_candidate_preview_from_news_defaults_to_candidate_status() -> None:
    preview = build_candidate_preview_from_news(
        trade_date="2026-06-01",
        query="金融界 主力资金 连续6天 净流出",
        items=[
            NewsItem(
                title="主力资金连续6天净流出",
                url="https://example.com/jrj/outflow",
                source=None,
                summary="主力资金连续6天净流出。",
                published_at="2026-06-01T18:00:00+08:00",
                matched_sector=None,
                weight=0.6,
            )
        ],
    )

    assert preview.valid_count == 1
    item = preview.items[0].item
    assert item is not None
    assert item.status == EvidenceStatus.CANDIDATE
    assert item.category == EvidenceCategory.CAPITAL_FLOW
    assert item.numbers["continuous_outflow_days"] == 6
