from __future__ import annotations

from typing import Any

from app.providers.market import MarketBreadth, MarketCloseSnapshot, ProviderFallbackError
from app.providers.tickflow import WatchlistQuote
from app.rules.scoring import RawSectorInput
from app.schemas.report import IndexSnapshot


EASY_TDX_INDEX_SYMBOLS: tuple[tuple[int, str, str], ...] = (
    (1, "000001", "上证指数"),
    (0, "399006", "创业板指"),
)
DEFAULT_BOARD_TOP_N = 12
MAX_FRONTLINE_STOCKS = 8


class EasyTdxMarketDataProvider:
    provider_name = "easy_tdx"

    def __init__(
        self,
        timeout_seconds: float = 12,
        client: object | None = None,
        board_top_n: int = DEFAULT_BOARD_TOP_N,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self._owns_client = client is None
        self._client = client
        self.board_top_n = board_top_n
        self._sector_frontline_stocks: dict[str, list[WatchlistQuote]] = {}

    def close(self) -> None:
        if not self._owns_client:
            return
        close = getattr(self._client, "close", None)
        if callable(close):
            close()
        self._client = None

    def get_close_snapshot(self, trade_date: str) -> MarketCloseSnapshot:
        equity_quotes = self._equity_quotes()
        if not equity_quotes:
            raise ProviderFallbackError("Easy TDX 行情数据不足")
        indices = self._indices()
        if not indices:
            raise ProviderFallbackError("Easy TDX 指数数据不足")
        raw_sectors = self._raw_sectors()
        if not raw_sectors:
            raise ProviderFallbackError("Easy TDX 板块数据不足")

        changes = [quote.pct_change for quote in equity_quotes if quote.pct_change is not None]
        if not changes:
            raise ProviderFallbackError("Easy TDX 行情数据不足")
        turnover_cny = round(sum(quote.turnover_cny or 0 for quote in equity_quotes) / 100_000_000, 2)
        return MarketCloseSnapshot(
            trade_date=trade_date,
            indices=indices,
            breadth=MarketBreadth(
                up_count=sum(1 for change in changes if change > 0),
                down_count=sum(1 for change in changes if change < 0),
                limit_up_count=sum(1 for change in changes if change >= 9.8),
                limit_down_count=sum(1 for change in changes if change <= -9.8),
            ),
            turnover_cny=turnover_cny,
            market_state_tags=_market_tags(changes, turnover_cny),
            raw_sectors=raw_sectors,
        )

    def get_sector_frontline_stocks(self, sector_name: str) -> list[WatchlistQuote]:
        return list(self._sector_frontline_stocks.get(sector_name, []))

    def _equity_quotes(self) -> list[WatchlistQuote]:
        category, sort_type, sort_order, fields = _easy_tdx_quote_list_args()
        frame = self._get_client().get_stock_quotes_list(
            category,
            count=5000,
            sort_type=sort_type,
            sort_order=sort_order,
            fields=fields,
        )
        return [_quote_from_row(row) for row in _frame_records(frame) if _is_regular_equity_row(row)]

    def _indices(self) -> list[IndexSnapshot]:
        frame = self._get_client().get_stock_quotes(
            [(market, code) for market, code, _name in EASY_TDX_INDEX_SYMBOLS]
        )
        names = {code: name for _market, code, name in EASY_TDX_INDEX_SYMBOLS}
        indices: list[IndexSnapshot] = []
        for row in _frame_records(frame):
            code = _str_value(row.get("code"))
            close = _float_value(row.get("close") or row.get("price"))
            pct_change = _pct_change_from_row(row)
            if not code or close is None or pct_change is None or code not in names:
                continue
            indices.append(
                IndexSnapshot(
                    name=_str_value(row.get("name")) or names[code],
                    code=code,
                    close=close,
                    pct_change=pct_change,
                )
            )
        return indices

    def _raw_sectors(self) -> list[RawSectorInput]:
        board_type = _easy_tdx_board_type()
        frame = self._get_client().get_board_ranking(
            board_type=board_type,
            top_n=self.board_top_n,
            sort_by="change_pct",
        )
        self._sector_frontline_stocks = {}
        sectors: list[RawSectorInput] = []
        for row in _frame_records(frame):
            name = _str_value(row.get("name"))
            code = _str_value(row.get("code"))
            if not name or not code:
                continue
            pct_change = _float_value(row.get("change_pct")) or 0.0
            up_count = int(_float_value(row.get("up_count")) or 0)
            down_count = int(_float_value(row.get("down_count")) or 0)
            member_count = int(_float_value(row.get("member_count")) or 0)
            denominator = up_count + down_count or member_count
            stock_up_ratio = (up_count / denominator) if denominator else 0.0
            turnover_cny = _float_value(row.get("amount")) or 0.0
            main_net_amount = _float_value(row.get("main_net_amount")) or 0.0
            sectors.append(
                RawSectorInput(
                    name=name,
                    pct_change=pct_change,
                    limit_up_count=int(_float_value(row.get("limit_up_count")) or 0),
                    stock_up_ratio=stock_up_ratio,
                    turnover_change=min(turnover_cny / 20_000_000_000, 1.0),
                    news_weight=min(max((abs(main_net_amount) / 5_000_000_000) + (pct_change / 20), 0.0), 1.0),
                )
            )
            self._sector_frontline_stocks[name] = self._frontline_stocks(code)
        return sorted(
            sectors,
            key=lambda sector: (sector.limit_up_count, sector.pct_change, sector.stock_up_ratio),
            reverse=True,
        )

    def _frontline_stocks(self, board_code: str) -> list[WatchlistQuote]:
        try:
            frame = self._get_client().get_board_members(board_code)
        except Exception:
            return []
        quotes = [
            _quote_from_row(row)
            for row in _frame_records(frame)
            if _is_regular_equity_row(row)
        ]
        ranked = sorted(
            [quote for quote in quotes if quote.pct_change is not None],
            key=lambda quote: ((quote.pct_change or 0), (quote.turnover_cny or 0)),
            reverse=True,
        )
        return ranked[:MAX_FRONTLINE_STOCKS]

    def _get_client(self) -> object:
        if self._client is None:
            self._client = _create_easy_tdx_client(self.timeout_seconds)
        return self._client


def _create_easy_tdx_client(timeout_seconds: float) -> object:
    try:
        from easy_tdx import MacClient
    except Exception as exc:
        raise ProviderFallbackError("easy-tdx 未安装") from exc
    client = MacClient.from_best_host(
        timeout=timeout_seconds,
        ping_timeout=min(timeout_seconds, 5.0),
    )
    client.connect()
    return client


def _easy_tdx_quote_list_args() -> tuple[object, object, object, object]:
    try:
        from easy_tdx import Category, SortOrder, SortType
        from easy_tdx.codec.bitmap import FieldBit, PresetField
    except Exception as exc:
        raise ProviderFallbackError("easy-tdx 未安装") from exc
    fields = (
        PresetField.BASIC
        + FieldBit.AMOUNT
        + FieldBit.TURNOVER
        + FieldBit.MAIN_NET_AMOUNT
    )
    return Category.A, SortType.CHANGE_PCT, SortOrder.DESC, fields


def _easy_tdx_board_type() -> object:
    try:
        from easy_tdx import BoardType
    except Exception as exc:
        raise ProviderFallbackError("easy-tdx 未安装") from exc
    return BoardType.HY


def _frame_records(frame: object) -> list[dict[str, Any]]:
    if frame is None:
        return []
    empty = getattr(frame, "empty", False)
    if empty:
        return []
    if isinstance(frame, list):
        return [row for row in frame if isinstance(row, dict)]
    to_dict = getattr(frame, "to_dict", None)
    if callable(to_dict):
        records = to_dict("records")
        if isinstance(records, list):
            return [row for row in records if isinstance(row, dict)]
    return []


def _quote_from_row(row: dict[str, Any]) -> WatchlistQuote:
    code = _str_value(row.get("code"))
    if not code:
        raise ProviderFallbackError("Easy TDX 响应缺少 code")
    pct_change = _pct_change_from_row(row)
    turnover_cny = _float_value(row.get("amount") or row.get("turnover_cny"))
    turnover_rate = _float_value(row.get("turnover") or row.get("turnover_rate"))
    return WatchlistQuote(
        symbol=_symbol_from_row(row),
        name=_str_value(row.get("name")),
        last_price=_float_value(row.get("close") or row.get("price")),
        pct_change=pct_change,
        turnover_cny=turnover_cny,
        turnover_rate=turnover_rate,
        capital_strength=_capital_strength_label(turnover_cny, turnover_rate, pct_change),
        volume=_float_value(row.get("vol") or row.get("volume")),
        quote_time=_quote_time_from_row(row),
    )


def _symbol_from_row(row: dict[str, Any]) -> str:
    code = _str_value(row.get("code"))
    market = int(_float_value(row.get("market")) or 0)
    suffix = "SH" if market == 1 else "BJ" if market == 2 else "SZ"
    return f"{code}.{suffix}"


def _is_regular_equity_row(row: dict[str, Any]) -> bool:
    code = _str_value(row.get("code"))
    if not code:
        return False
    name = (_str_value(row.get("name")) or "").upper()
    if "ST" in name:
        return False
    market = int(_float_value(row.get("market")) or 0)
    if market == 2:
        return False
    if market == 1:
        return code.startswith(("60", "68"))
    return code.startswith(("00", "30"))


def _pct_change_from_row(row: dict[str, Any]) -> float | None:
    direct = _float_value(row.get("change_pct") or row.get("pct_change"))
    if direct is not None:
        return direct * 100 if abs(direct) <= 1 else direct
    close = _float_value(row.get("close") or row.get("price"))
    pre_close = _float_value(row.get("pre_close"))
    if close is None or pre_close is None or pre_close == 0:
        return None
    return (close - pre_close) / pre_close * 100


def _quote_time_from_row(row: dict[str, Any]) -> str | None:
    date_value = _str_value(row.get("server_update_date"))
    time_value = _str_value(row.get("server_update_time"))
    if date_value and time_value:
        return f"{date_value} {time_value}"
    return _str_value(row.get("quote_time") or row.get("time"))


def _market_tags(changes: list[float], turnover_cny: float) -> list[str]:
    up_count = sum(1 for change in changes if change > 0)
    down_count = sum(1 for change in changes if change < 0)
    if up_count > down_count * 1.5:
        breadth = "普涨"
    elif down_count > up_count * 1.5:
        breadth = "普跌"
    else:
        breadth = "分化"
    return [breadth, "放量" if turnover_cny >= 10000 else "缩量"]


def _capital_strength_label(
    turnover_cny: float | None,
    turnover_rate: float | None,
    pct_change: float | None,
) -> str | None:
    if turnover_cny is None and turnover_rate is None:
        return None
    turnover_yi = (turnover_cny or 0) / 100_000_000
    rate = turnover_rate or 0
    change = pct_change or 0
    if turnover_yi >= 30 and rate >= 20 and change >= 5:
        return "高换手强承接"
    if turnover_yi >= 10 or (rate >= 8 and change >= 5):
        return "强"
    if turnover_yi >= 3 or rate >= 5:
        return "温和放量"
    if rate >= 25 and change < 5:
        return "高换手分歧"
    return "一般"


def _float_value(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _str_value(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
