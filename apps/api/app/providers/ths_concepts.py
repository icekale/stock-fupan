from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from app.rules.scoring import RawSectorInput


CONCEPT_ALIASES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("PCB", ("PCB",)),
    ("半导体", ("半导体", "芯片", "封装", "封测", "集成电路")),
    ("新材料", ("新材料", "材料", "培育钻石", "复合材料")),
    ("环保", ("环保", "节能环保", "水务", "固废", "污水")),
    ("机器人", ("机器人", "人形机器人", "自动化", "伺服", "工业母机")),
    ("有色金属", ("有色金属", "贵金属", "黄金", "铜", "铝", "锂", "稀土", "小金属")),
    ("电力设备", ("电力设备", "智能电网", "输变电", "电网设备", "特高压")),
    ("电力", ("电力", "风电", "光伏", "核电", "发电", "火电")),
)


@dataclass(frozen=True)
class ConceptBoardSnapshot:
    pct_change: float | None = None
    turnover_yi: float | None = None
    net_inflow_yi: float | None = None
    up_count: int | None = None
    down_count: int | None = None


class ThsConceptBoardProvider:
    provider_name = "ths_concept"

    def __init__(self, akshare_module: object | None = None) -> None:
        self._akshare_module = akshare_module
        self._concept_names_cache: list[str] | None = None

    def close(self) -> None:
        pass

    def build_sector_input(
        self,
        sector_name: str,
        quotes: list[object],
        trade_date: str | None = None,
    ) -> RawSectorInput | None:
        if not sector_name:
            return None
        quote_changes = _quote_changes(quotes)
        if not quote_changes:
            return None

        concept_name = self._resolve_concept_name(sector_name) or sector_name
        snapshot = self._board_snapshot(concept_name, trade_date)
        pct_change = snapshot.pct_change if snapshot and snapshot.pct_change is not None else _average(quote_changes)
        up_count, down_count = (
            (snapshot.up_count, snapshot.down_count)
            if snapshot and snapshot.up_count is not None and snapshot.down_count is not None
            else _quote_up_down_counts(quote_changes)
        )
        turnover_change = _turnover_change(snapshot, quotes)
        limit_up_count = _limit_up_count(quote_changes)
        stock_up_ratio = _stock_up_ratio(up_count, down_count, quote_changes)
        news_weight = min(
            max((limit_up_count * 0.25) + (pct_change / 20.0) + max(turnover_change, 0.0) * 0.2, 0.0),
            1.0,
        )
        return RawSectorInput(
            name=concept_name,
            pct_change=round(pct_change, 2),
            limit_up_count=limit_up_count,
            stock_up_ratio=round(stock_up_ratio, 4),
            turnover_change=round(turnover_change, 4),
            news_weight=round(news_weight, 4),
        )

    def _board_snapshot(self, concept_name: str, trade_date: str | None) -> ConceptBoardSnapshot | None:
        ak = self._akshare()
        if ak is None:
            return None
        if not concept_name:
            return None

        info_rows = self._safe_rows(self._call_akshare(ak, "stock_board_concept_info_ths", symbol=concept_name))
        index_rows = self._safe_rows(
            self._call_akshare(
                ak,
                "stock_board_concept_index_ths",
                symbol=concept_name,
                start_date=_start_date_for_trade_date(trade_date),
                end_date=_trade_date_as_yyyymmdd(trade_date),
            )
        )
        pct_change = _info_pct_change(info_rows)
        if pct_change is None:
            pct_change = _index_pct_change(index_rows)
        turnover_yi = _info_float(info_rows, ("成交额(亿)", "成交额"))
        net_inflow_yi = _info_float(info_rows, ("资金净流入(亿)", "资金净流入"))
        up_count, down_count = _info_balance(info_rows)
        return ConceptBoardSnapshot(
            pct_change=pct_change,
            turnover_yi=turnover_yi,
            net_inflow_yi=net_inflow_yi,
            up_count=up_count,
            down_count=down_count,
        )

    def _resolve_concept_name(self, sector_name: str) -> str | None:
        candidates = [sector_name, *_sector_aliases(sector_name)]
        concept_names = self._concept_names()
        if not concept_names:
            return candidates[0]
        for candidate in candidates:
            if candidate in concept_names:
                return candidate
        for concept_name in concept_names:
            if any(alias in concept_name or concept_name in alias for alias in candidates):
                return concept_name
        return candidates[0]

    def _concept_names(self) -> list[str]:
        if self._concept_names_cache is not None:
            return self._concept_names_cache
        ak = self._akshare()
        if ak is None:
            self._concept_names_cache = []
            return self._concept_names_cache
        rows = self._safe_rows(self._call_akshare(ak, "stock_board_concept_name_ths"))
        names: list[str] = []
        for row in rows:
            extracted = _best_text_values(row)
            if extracted:
                names.append(extracted[0])
        self._concept_names_cache = _dedupe(names)
        return self._concept_names_cache

    def _akshare(self) -> object | None:
        if self._akshare_module is not None:
            return self._akshare_module
        try:
            import akshare as ak
        except Exception:
            return None
        self._akshare_module = ak
        return ak

    def _call_akshare(self, ak: object, name: str, **kwargs: object) -> object | None:
        func = getattr(ak, name, None)
        if not callable(func):
            return None
        try:
            return func(**kwargs)
        except Exception:
            return None

    def _safe_rows(self, frame: object | None) -> list[dict[str, Any]]:
        if frame is None:
            return []
        to_dict = getattr(frame, "to_dict", None)
        if callable(to_dict):
            try:
                rows = to_dict(orient="records")
            except Exception:
                rows = None
            if isinstance(rows, list):
                return [row for row in rows if isinstance(row, dict)]
        if isinstance(frame, list):
            return [row for row in frame if isinstance(row, dict)]
        if isinstance(frame, dict):
            return [frame]
        return []


def _sector_aliases(sector_name: str) -> tuple[str, ...]:
    for name, aliases in CONCEPT_ALIASES:
        if name == sector_name:
            return aliases
    return ()


def _best_text_values(row: dict[str, Any]) -> list[str]:
    preferred_keys = (
        "板块名称",
        "名称",
        "概念名称",
        "name",
        "symbol",
        "行业名称",
        "板块",
    )
    values: list[str] = []
    for key in preferred_keys:
        value = row.get(key)
        if isinstance(value, str):
            text = value.strip()
            if text:
                values.append(text)
    if values:
        return values
    fallback = [
        str(value).strip()
        for value in row.values()
        if isinstance(value, str) and str(value).strip()
    ]
    return [value for value in fallback if not _looks_like_number(value)]


def _info_pct_change(rows: list[dict[str, Any]]) -> float | None:
    value = _info_value(rows, ("板块涨幅", "涨跌幅", "涨幅"))
    return _parse_float(value)


def _info_float(rows: list[dict[str, Any]], keys: tuple[str, ...]) -> float | None:
    return _parse_float(_info_value(rows, keys))


def _info_balance(rows: list[dict[str, Any]]) -> tuple[int | None, int | None]:
    value = _info_value(rows, ("涨跌家数", "涨跌比"))
    if not value:
        up = _parse_int(_info_value(rows, ("上涨家数", "上涨数量")))
        down = _parse_int(_info_value(rows, ("下跌家数", "下跌数量")))
        return up, down
    parts = [part.strip() for part in str(value).replace("，", "/").split("/") if part.strip()]
    if len(parts) >= 2:
        return _parse_int(parts[0]), _parse_int(parts[1])
    return None, None


def _info_value(rows: list[dict[str, Any]], keys: tuple[str, ...]) -> str | None:
    for row in rows:
        for key in keys:
            value = row.get(key)
            if value is not None and str(value).strip():
                return str(value).strip()
        if "项目" in row and "值" in row:
            project = str(row.get("项目") or "").strip()
            if project in keys:
                value = row.get("值")
                if value is not None and str(value).strip():
                    return str(value).strip()
    return None


def _index_pct_change(rows: list[dict[str, Any]]) -> float | None:
    closes: list[float] = []
    for row in rows:
        close = _parse_float(_first_present(row, ("收盘价", "收盘", "close")))
        if close is not None:
            closes.append(close)
    if len(closes) < 2 or closes[-2] == 0:
        return None
    return (closes[-1] - closes[-2]) / closes[-2] * 100.0


def _turnover_change(snapshot: ConceptBoardSnapshot | None, quotes: list[object]) -> float:
    quote_turnover = sum(_quote_turnover(quote) for quote in quotes if _quote_turnover(quote) is not None)
    if snapshot is None:
        return min(quote_turnover / 10_000_000_000, 1.0) if quote_turnover else 0.0
    if snapshot.net_inflow_yi is not None and snapshot.turnover_yi:
        return snapshot.net_inflow_yi / max(snapshot.turnover_yi, 1.0)
    if snapshot.net_inflow_yi is not None:
        return snapshot.net_inflow_yi / 100.0
    if snapshot.turnover_yi is not None:
        return snapshot.turnover_yi / 1000.0
    return min(quote_turnover / 10_000_000_000, 1.0) if quote_turnover else 0.0


def _quote_changes(quotes: list[object]) -> list[float]:
    return [change for change in (_quote_pct_change(quote) for quote in quotes) if change is not None]


def _quote_pct_change(quote: object) -> float | None:
    return _parse_float(getattr(quote, "pct_change", None))


def _quote_turnover(quote: object) -> float | None:
    return _parse_float(getattr(quote, "turnover_cny", None))


def _quote_up_down_counts(changes: list[float]) -> tuple[int, int]:
    return sum(1 for change in changes if change > 0), sum(1 for change in changes if change < 0)


def _stock_up_ratio(up_count: int | None, down_count: int | None, changes: list[float]) -> float:
    if up_count is not None and down_count is not None:
        total = up_count + down_count
        if total > 0:
            return up_count / total
    if not changes:
        return 0.0
    return sum(1 for change in changes if change > 0) / len(changes)


def _limit_up_count(changes: list[float]) -> int:
    return sum(1 for change in changes if change >= 9.8)


def _average(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _parse_float(value: object | None) -> float | None:
    if value is None:
        return None
    cleaned = str(value).replace("%", "").replace("，", "").replace(",", "").replace("+", "").strip()
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _parse_int(value: object | None) -> int | None:
    number = _parse_float(value)
    if number is None:
        return None
    return int(number)


def _first_present(row: dict[str, Any], keys: tuple[str, ...]) -> object | None:
    for key in keys:
        value = row.get(key)
        if value is not None and str(value).strip():
            return value
    return None


def _looks_like_number(value: str) -> bool:
    stripped = value.replace("%", "").replace("+", "").replace("-", "").replace(".", "")
    return stripped.isdigit()


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        output.append(value)
    return output


def _trade_date_as_yyyymmdd(trade_date: str | None) -> str:
    if not trade_date:
        return date.today().strftime("%Y%m%d")
    return trade_date.replace("-", "")


def _start_date_for_trade_date(trade_date: str | None) -> str:
    if not trade_date:
        return (date.today() - timedelta(days=10)).strftime("%Y%m%d")
    try:
        parsed = datetime.strptime(trade_date, "%Y-%m-%d").date()
    except ValueError:
        return trade_date.replace("-", "")
    return (parsed - timedelta(days=10)).strftime("%Y%m%d")
