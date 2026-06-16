from pydantic import BaseModel, Field
from sqlalchemy import Engine, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.db.models import WatchlistGroup, WatchlistStock
from app.db.session import session_scope
from app.watchlist.parser import WatchlistItem, _infer_exchange


DEFAULT_GROUP_NAME = "自选"


class WatchlistGroupDto(BaseModel):
    id: int
    name: str
    is_default: bool
    sort_order: int


class WatchlistStockDto(BaseModel):
    id: int
    symbol: str
    code: str
    exchange: str
    name: str | None = None
    status: str = "观察中"
    tags: list[str] = Field(default_factory=list)
    entry_reason: str | None = None
    planned_buy_price: str | None = None
    invalid_condition: str | None = None
    themes: list[str] = Field(default_factory=list)
    last_review_conclusion: str | None = None
    today_risk_hint: str | None = None
    groups: list[WatchlistGroupDto] = Field(default_factory=list)


class WatchlistPoolState(BaseModel):
    groups: list[WatchlistGroupDto]
    stocks: list[WatchlistStockDto]


class WatchlistPoolService:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def get_state(self) -> WatchlistPoolState:
        return self.get_pool()

    def get_pool(self) -> WatchlistPoolState:
        with session_scope(self.engine) as session:
            self._ensure_default_group(session)
            groups = (
                session.execute(
                    select(WatchlistGroup).order_by(WatchlistGroup.sort_order, WatchlistGroup.id)
                )
                .scalars()
                .all()
            )
            stocks = session.execute(select(WatchlistStock).order_by(WatchlistStock.id)).scalars().all()
            return WatchlistPoolState(
                groups=[_group_dto(group) for group in groups],
                stocks=[_stock_dto(stock) for stock in stocks],
            )

    def ensure_default_group(self) -> WatchlistGroupDto:
        with session_scope(self.engine) as session:
            return _group_dto(self._ensure_default_group(session))

    def create_group(self, name: str) -> WatchlistGroupDto:
        normalized_name = _clean_name(name)
        with session_scope(self.engine) as session:
            existing = self._find_group_by_name(session, normalized_name)
            if existing is not None:
                raise ValueError("分组名已存在")
            sort_orders = session.execute(select(WatchlistGroup.sort_order)).scalars().all()
            group = WatchlistGroup(
                name=normalized_name,
                is_default=False,
                sort_order=(max(sort_orders) + 1) if sort_orders else 1,
            )
            session.add(group)
            session.flush()
            return _group_dto(group)

    def delete_group(self, group_id: int) -> None:
        with session_scope(self.engine) as session:
            group = session.get(WatchlistGroup, group_id)
            if group is None:
                raise ValueError("分组不存在")
            if group.is_default:
                raise ValueError("默认分组不可删除")
            session.delete(group)

    def rename_group(self, group_id: int, name: str) -> WatchlistGroupDto:
        normalized_name = _clean_name(name)
        with session_scope(self.engine) as session:
            group = session.get(WatchlistGroup, group_id)
            if group is None:
                raise ValueError(f"Watchlist group not found: {group_id}")
            existing = self._find_group_by_name(session, normalized_name)
            if existing is not None and existing.id != group.id:
                raise ValueError("分组名已存在")
            group.name = normalized_name
            session.flush()
            return _group_dto(group)

    def add_stock(
        self,
        *,
        symbol: str,
        code: str | None = None,
        exchange: str | None = None,
        name: str | None = None,
    ) -> WatchlistStockDto:
        normalized = _normalize_symbol(symbol, code=code, exchange=exchange)
        with session_scope(self.engine) as session:
            default_group = self._ensure_default_group(session)
            stock = self._upsert_stock_in_session(
                session,
                symbol=normalized["symbol"],
                code=normalized["code"],
                exchange=normalized["exchange"],
                name=name,
            )
            if default_group not in stock.groups:
                stock.groups.append(default_group)
            session.flush()
            return _stock_dto(stock)

    def get_stock(self, stock_id: int | str) -> WatchlistStockDto:
        with session_scope(self.engine) as session:
            return _stock_dto(self._get_stock(session, stock_id))

    def update_stock_identity(
        self,
        stock_id: int | str,
        *,
        symbol: str | None = None,
        code: str | None = None,
        exchange: str | None = None,
        name: str | None = None,
    ) -> WatchlistStockDto:
        with session_scope(self.engine) as session:
            stock = self._get_stock(session, stock_id)
            normalized = None
            if symbol is not None or code is not None or exchange is not None:
                normalized = _normalize_symbol(
                    symbol or stock.symbol,
                    code=code or stock.code,
                    exchange=exchange or stock.exchange,
                )
                stock.symbol = normalized["symbol"]
                stock.code = normalized["code"]
                stock.exchange = normalized["exchange"]
            if name is not None:
                stock.name = name
            session.flush()
            return _stock_dto(stock)

    def upsert_items(self, items: list[WatchlistItem]) -> None:
        with session_scope(self.engine) as session:
            self.upsert_items_in_session(session, items)

    def upsert_items_in_session(self, session, items: list[WatchlistItem]) -> None:
        default_group = self._ensure_default_group(session)
        for item in items:
            stock = self._upsert_stock_in_session(
                session,
                symbol=item.symbol,
                code=item.code,
                exchange=item.exchange,
                name=item.name,
            )
            if all(existing.id != default_group.id for existing in stock.groups):
                stock.groups.append(default_group)

    def set_stock_groups(self, stock_id: int | str, group_ids: list[int]) -> WatchlistStockDto:
        with session_scope(self.engine) as session:
            stock = self._get_stock(session, stock_id)
            stock.groups = self._groups_by_ids(session, group_ids)
            session.flush()
            return _stock_dto(stock)

    def add_stock_to_group(self, stock_id: int | str, group_name: str) -> WatchlistStockDto:
        with session_scope(self.engine) as session:
            stock = self._get_stock(session, stock_id)
            group = self._find_group_by_name(session, _clean_name(group_name))
            if group is None:
                sort_orders = session.execute(select(WatchlistGroup.sort_order)).scalars().all()
                group = WatchlistGroup(
                    name=_clean_name(group_name),
                    is_default=False,
                    sort_order=(max(sort_orders) + 1) if sort_orders else 1,
                )
                session.add(group)
                session.flush()
            if group not in stock.groups:
                stock.groups.append(group)
            session.flush()
            return _stock_dto(stock)

    def set_stock_tags(self, stock_id: int | str, tags: list[str]) -> WatchlistStockDto:
        with session_scope(self.engine) as session:
            stock = self._get_stock(session, stock_id)
            stock.tags = _clean_list(tags)
            session.flush()
            return _stock_dto(stock)

    def set_stock_status(self, stock_id: int | str, status: str) -> WatchlistStockDto:
        cleaned = status.strip()
        if cleaned not in {"观察中", "持有中"}:
            raise ValueError("股票状态仅支持 观察中 或 持有中")
        with session_scope(self.engine) as session:
            stock = self._get_stock(session, stock_id)
            stock.status = cleaned
            session.flush()
            return _stock_dto(stock)

    def update_observation_plan(
        self,
        stock_id: int | str,
        *,
        entry_reason: str | None = None,
        planned_buy_price: str | None = None,
        invalid_condition: str | None = None,
        themes: list[str] | None = None,
        last_review_conclusion: str | None = None,
        today_risk_hint: str | None = None,
    ) -> WatchlistStockDto:
        with session_scope(self.engine) as session:
            stock = self._get_stock(session, stock_id)
            stock.entry_reason = entry_reason
            stock.planned_buy_price = planned_buy_price
            stock.invalid_condition = invalid_condition
            if themes is not None:
                stock.themes = _clean_list(themes)
            stock.last_review_conclusion = last_review_conclusion
            stock.today_risk_hint = today_risk_hint
            session.flush()
            return _stock_dto(stock)

    def update_review_result(
        self,
        stock_id: int | str,
        *,
        last_review_conclusion: str | None = None,
        today_risk_hint: str | None = None,
    ) -> WatchlistStockDto:
        with session_scope(self.engine) as session:
            stock = self._get_stock(session, stock_id)
            if last_review_conclusion is not None:
                stock.last_review_conclusion = last_review_conclusion.strip()
            if today_risk_hint is not None:
                stock.today_risk_hint = today_risk_hint.strip()
            session.flush()
            return _stock_dto(stock)

    def _ensure_default_group(self, session) -> WatchlistGroup:
        group = self._find_group_by_name(session, DEFAULT_GROUP_NAME)
        if group is not None:
            if not group.is_default:
                group.is_default = True
            return group
        group = WatchlistGroup(name=DEFAULT_GROUP_NAME, is_default=True, sort_order=0)
        session.add(group)
        session.flush()
        return group

    def _upsert_stock_in_session(
        self,
        session,
        *,
        symbol: str,
        code: str,
        exchange: str,
        name: str | None,
    ) -> WatchlistStock:
        if session.bind is not None and session.bind.dialect.name == "sqlite":
            values = {
                "symbol": symbol,
                "code": code,
                "exchange": exchange,
            }
            if name is not None:
                values["name"] = name
            stmt = sqlite_insert(WatchlistStock).values(**values)
            update_values = {
                "code": code,
                "exchange": exchange,
            }
            if name is not None:
                update_values["name"] = name
            stmt = stmt.on_conflict_do_update(
                index_elements=[WatchlistStock.symbol],
                set_=update_values,
            )
            session.execute(stmt)
            return self._find_stock_by_symbol(session, symbol)  # type: ignore[return-value]

        stock = self._find_stock_by_symbol(session, symbol)
        if stock is None:
            stock = WatchlistStock(
                symbol=symbol,
                code=code,
                exchange=exchange,
                name=name,
                status="观察中",
                tags=[],
                themes=[],
            )
            session.add(stock)
            session.flush()
            return stock
        stock.code = code
        stock.exchange = exchange
        if name:
            stock.name = name
        return stock

    def _get_stock(self, session, stock_id: int | str) -> WatchlistStock:
        if isinstance(stock_id, int):
            stock = session.get(WatchlistStock, stock_id)
        else:
            stock = self._find_stock_by_symbol(session, stock_id)
        if stock is None:
            raise ValueError("股票不存在")
        return stock

    def _find_stock_by_symbol(self, session, symbol: str) -> WatchlistStock | None:
        return session.execute(
            select(WatchlistStock).where(WatchlistStock.symbol == symbol).limit(1)
        ).scalar_one_or_none()

    def _find_group_by_name(self, session, name: str) -> WatchlistGroup | None:
        return session.execute(
            select(WatchlistGroup).where(WatchlistGroup.name == name).limit(1)
        ).scalar_one_or_none()

    def _groups_by_ids(self, session, group_ids: list[int]) -> list[WatchlistGroup]:
        groups = (
            session.execute(
                select(WatchlistGroup)
                .where(WatchlistGroup.id.in_(group_ids))
                .order_by(WatchlistGroup.sort_order, WatchlistGroup.id)
            )
            .scalars()
            .all()
        )
        if len(groups) != len(set(group_ids)):
            raise ValueError("分组不存在")
        return list(groups)


def _stock_dto(stock: WatchlistStock) -> WatchlistStockDto:
    groups = sorted(stock.groups, key=lambda group: (group.sort_order, group.id))
    return WatchlistStockDto(
        id=stock.id,
        symbol=stock.symbol,
        code=stock.code,
        exchange=stock.exchange,
        name=stock.name,
        status=stock.status or "观察中",
        tags=stock.tags or [],
        entry_reason=stock.entry_reason,
        planned_buy_price=stock.planned_buy_price,
        invalid_condition=stock.invalid_condition,
        themes=stock.themes or [],
        last_review_conclusion=stock.last_review_conclusion,
        today_risk_hint=stock.today_risk_hint,
        groups=[_group_dto(group) for group in groups],
    )


def _group_dto(group: WatchlistGroup) -> WatchlistGroupDto:
    return WatchlistGroupDto(
        id=group.id,
        name=group.name,
        is_default=group.is_default,
        sort_order=group.sort_order,
    )


def _clean_name(name: str) -> str:
    cleaned = name.strip()
    if not cleaned:
        raise ValueError("Watchlist group name cannot be empty")
    return cleaned


def _clean_list(values: list[str]) -> list[str]:
    return [value.strip() for value in values if value.strip()]


def _normalize_symbol(
    symbol: str,
    *,
    code: str | None = None,
    exchange: str | None = None,
) -> dict[str, str]:
    cleaned_symbol = symbol.strip().upper()
    if "." in cleaned_symbol:
        parsed_code, parsed_exchange = cleaned_symbol.split(".", 1)
    else:
        parsed_code = code or cleaned_symbol[-6:]
        parsed_exchange = exchange or _infer_exchange(parsed_code)
    final_code = (code or parsed_code).strip()
    final_exchange = (exchange or parsed_exchange or "").strip().upper()
    if final_exchange not in {"SH", "SZ", "BJ"}:
        raise ValueError("无法识别股票交易所")
    return {
        "symbol": f"{final_code}.{final_exchange}",
        "code": final_code,
        "exchange": final_exchange,
    }
