from pathlib import Path

from app.db.models import WatchlistStock, WatchlistStockGroup
from app.db.session import create_sqlite_engine, init_db, session_scope
from app.watchlist.pool_service import WatchlistPoolService
from app.watchlist.service import WatchlistImportService


def test_pool_state_creates_default_group(tmp_path: Path) -> None:
    engine = create_sqlite_engine(f"sqlite:///{tmp_path / 'watchlist.db'}")
    init_db(engine)
    service = WatchlistPoolService(engine)

    state = service.get_state()

    assert [group.name for group in state.groups] == ["自选"]
    assert state.groups[0].is_default is True
    assert state.stocks == []


def test_stock_can_belong_to_multiple_groups(tmp_path: Path) -> None:
    engine = create_sqlite_engine(f"sqlite:///{tmp_path / 'watchlist.db'}")
    init_db(engine)
    service = WatchlistPoolService(engine)

    momentum = service.create_group("动量")
    ai = service.create_group("AI")
    service.add_stock(symbol="600000.SH", code="600000", exchange="SH", name="浦发银行")
    stock = service.set_stock_groups("600000.SH", [momentum.id, ai.id])

    assert stock.symbol == "600000.SH"
    assert [group.name for group in stock.groups] == ["动量", "AI"]
    state_stock = service.get_state().stocks[0]
    assert [group.name for group in state_stock.groups] == ["动量", "AI"]


def test_stock_identity_can_be_updated_without_recreating_stock(tmp_path: Path) -> None:
    engine = create_sqlite_engine(f"sqlite:///{tmp_path / 'watchlist.db'}")
    init_db(engine)
    service = WatchlistPoolService(engine)
    stock = service.add_stock(symbol="600563.SH", name="法拉电子")

    updated = service.update_stock_identity(stock.id, name="法拉电子股份")

    assert updated.id == stock.id
    assert updated.symbol == "600563.SH"
    assert updated.name == "法拉电子股份"


def test_deleting_custom_group_keeps_stocks(tmp_path: Path) -> None:
    engine = create_sqlite_engine(f"sqlite:///{tmp_path / 'watchlist.db'}")
    init_db(engine)
    service = WatchlistPoolService(engine)

    custom = service.create_group("观察")
    service.add_stock(symbol="000001.SZ", code="000001", exchange="SZ", name="平安银行")
    service.set_stock_groups("000001.SZ", [custom.id])

    service.delete_group(custom.id)

    state = service.get_state()
    assert [group.name for group in state.groups] == ["自选"]
    assert [stock.symbol for stock in state.stocks] == ["000001.SZ"]
    assert state.stocks[0].groups == []


def test_observation_plan_fields_and_default_group_delete_rule(tmp_path: Path) -> None:
    engine = create_sqlite_engine(f"sqlite:///{tmp_path / 'watchlist.db'}")
    init_db(engine)
    service = WatchlistPoolService(engine)

    default_group = service.ensure_default_group()
    stock = service.add_stock(symbol="300750.SZ", name="宁德时代")

    updated = service.update_observation_plan(
        stock.id,
        entry_reason="储能方向观察",
        planned_buy_price="回踩MA20",
        invalid_condition="跌破平台",
        themes=["储能", "新能源"],
        last_review_conclusion="趋势保持",
        today_risk_hint="放量下跌需复核",
    )

    assert updated.entry_reason == "储能方向观察"
    assert updated.planned_buy_price == "回踩MA20"
    assert updated.invalid_condition == "跌破平台"
    assert updated.themes == ["储能", "新能源"]
    assert updated.last_review_conclusion == "趋势保持"
    assert updated.today_risk_hint == "放量下跌需复核"
    try:
        service.delete_group(default_group.id)
    except ValueError as exc:
        assert "默认分组不可删除" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_import_text_upserts_durable_stocks(tmp_path: Path) -> None:
    engine = create_sqlite_engine(f"sqlite:///{tmp_path / 'watchlist.db'}")
    init_db(engine)
    import_service = WatchlistImportService(engine=engine, snapshot_root=tmp_path / "watchlists")
    pool_service = WatchlistPoolService(engine)

    import_service.import_text(
        "代码,名称\n600000,浦发银行\n000001,平安银行\n",
        source_name="manual.csv",
    )
    import_service.import_text(
        "代码,名称\n600000,浦发银行股份\n",
        source_name="manual.csv",
    )

    state = pool_service.get_state()
    assert [stock.symbol for stock in state.stocks] == ["600000.SH", "000001.SZ"]
    assert state.stocks[0].name == "浦发银行股份"
    assert [group.name for group in state.stocks[0].groups] == ["自选"]
    with session_scope(engine) as session:
        assert session.query(WatchlistStock).count() == 2
        assert session.query(WatchlistStockGroup).count() == 2


def test_rename_group_rejects_duplicate_name(tmp_path: Path) -> None:
    engine = create_sqlite_engine(f"sqlite:///{tmp_path / 'watchlist.db'}")
    init_db(engine)
    service = WatchlistPoolService(engine)
    service.create_group("MLCC")
    duplicate = service.create_group("电力")

    try:
        service.rename_group(duplicate.id, "MLCC")
    except ValueError as exc:
        assert "分组名已存在" in str(exc)
    else:
        raise AssertionError("expected ValueError")
