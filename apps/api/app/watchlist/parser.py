import csv
import io
import re
from typing import Literal

from pydantic import BaseModel


Exchange = Literal["SH", "SZ", "BJ"]


class WatchlistItem(BaseModel):
    symbol: str
    code: str
    exchange: Exchange
    name: str | None = None
    source: str = "import"


class WatchlistParseResult(BaseModel):
    items: list[WatchlistItem]
    warnings: list[str] = []


_CODE_RE = re.compile(r"(?i)(?:\b(?P<prefix>SH|SZ|BJ)[.:-]?)?(?P<code>\d{6})(?:[.:-]?(?P<suffix>SH|SZ|BJ)\b)?")
_INVALID_TOKEN_RE = re.compile(
    r"(?i)\b(?=[a-z0-9]*\d)(?=[a-z0-9]*[a-z])[a-z0-9]{5,12}\b|\b\d{1,5}\b|\b\d{7,12}\b"
)


def parse_watchlist_text(content: str, source_name: str = "manual.txt") -> WatchlistParseResult:
    rows = _parse_csv_rows(content) if source_name.lower().endswith(".csv") else []
    if rows:
        return _parse_rows(rows)
    return _parse_free_text(content)


def _parse_rows(rows: list[dict[str, str]]) -> WatchlistParseResult:
    seen: set[str] = set()
    items: list[WatchlistItem] = []
    warnings: list[str] = []
    for row in rows:
        code_text = _first_value(row, "code", "代码", "symbol", "证券代码")
        name = _first_value(row, "name", "名称", "证券名称") or None
        item = _item_from_token(code_text, name=name)
        if item is None:
            if code_text:
                warnings.append(f"无法识别股票代码: {code_text}")
            continue
        if item.symbol not in seen:
            seen.add(item.symbol)
            items.append(item)
    return WatchlistParseResult(items=items, warnings=warnings)


def _parse_free_text(content: str) -> WatchlistParseResult:
    seen: set[str] = set()
    items: list[WatchlistItem] = []
    warnings: list[str] = []
    consumed_spans: list[tuple[int, int]] = []
    for match in _CODE_RE.finditer(content):
        item = _item_from_match(match)
        if item is None:
            continue
        consumed_spans.append(match.span())
        if item.symbol not in seen:
            seen.add(item.symbol)
            items.append(item)

    for match in _INVALID_TOKEN_RE.finditer(content):
        if any(start <= match.start() and match.end() <= end for start, end in consumed_spans):
            continue
        warnings.append(f"无法识别股票代码: {match.group(0)}")
    return WatchlistParseResult(items=items, warnings=warnings)


def _parse_csv_rows(content: str) -> list[dict[str, str]]:
    sample = content.encode("utf-8", errors="ignore").decode("utf-8-sig", errors="ignore")
    reader = csv.DictReader(io.StringIO(sample))
    if not reader.fieldnames:
        return []
    return [{str(key).strip(): str(value or "").strip() for key, value in row.items()} for row in reader]


def _first_value(row: dict[str, str], *keys: str) -> str:
    normalized = {key.strip().lower(): value for key, value in row.items()}
    for key in keys:
        value = normalized.get(key.lower())
        if value:
            return value.strip()
    return ""


def _item_from_token(token: str, name: str | None = None) -> WatchlistItem | None:
    match = _CODE_RE.search(token)
    if match is None:
        return None
    return _item_from_match(match, name=name)


def _item_from_match(match: re.Match[str], name: str | None = None) -> WatchlistItem | None:
    code = match.group("code")
    prefix = match.group("prefix")
    suffix = match.group("suffix")
    exchange = _infer_exchange(code, explicit=(suffix or prefix))
    if exchange is None:
        return None
    return WatchlistItem(
        symbol=f"{code}.{exchange}",
        code=code,
        exchange=exchange,
        name=name,
    )


def _infer_exchange(code: str, explicit: str | None = None) -> Exchange | None:
    if explicit:
        normalized = explicit.upper()
        if normalized in {"SH", "SZ", "BJ"}:
            return normalized  # type: ignore[return-value]
    if code.startswith("6"):
        return "SH"
    if code.startswith(("0", "3")):
        return "SZ"
    if code.startswith(("4", "8")):
        return "BJ"
    return None
