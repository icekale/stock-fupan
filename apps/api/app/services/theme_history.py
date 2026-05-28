from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from html.parser import HTMLParser

from app.providers.tickflow import TickFlowQuoteProvider, WatchlistQuote
from app.schemas.report import SectorCandidate
from app.schemas.structured_review import HistoricalThemeReview


VERSION_PATTERN = re.compile(r"^v(\d+)$")
TRADE_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def load_previous_strong_themes(
    reports_root: Path,
    trade_date: str,
    current_sectors: list[SectorCandidate],
    previous_review_html_path: Path | None = None,
    tickflow_provider: TickFlowQuoteProvider | None = None,
    max_items: int = 8,
) -> list[HistoricalThemeReview]:
    reviews: list[HistoricalThemeReview] = []
    if previous_review_html_path is not None:
        reviews.extend(load_previous_review_html_themes(previous_review_html_path, current_sectors, max_items=max_items))
    snapshot = _latest_previous_snapshot(reports_root, trade_date)
    if snapshot:
        reviews.extend(_build_historical_theme_reviews(snapshot, current_sectors, max_items=max_items))
    return _attach_current_stock_checks(
        _dedupe_reviews(reviews)[:max_items],
        previous_review_html_path=previous_review_html_path,
        tickflow_provider=tickflow_provider,
    )


def load_previous_review_html_themes(
    html_path: Path,
    current_sectors: list[SectorCandidate],
    max_items: int = 8,
) -> list[HistoricalThemeReview]:
    try:
        text = _html_text(html_path.read_text(encoding="utf-8"))
    except OSError:
        return []
    current_by_name = {sector.name: sector for sector in current_sectors}
    rows = _reference_sustainability_rows(text)
    reviews = []
    for row in rows:
        current_sector = _matching_current_sector(row["theme"], current_by_name)
        reviews.append(
            HistoricalThemeReview(
                theme=row["theme"],
                previous_status=f"上一复盘持续性{row['rating']}",
                current_status=_current_status(current_sector),
                judgement=_judgement(_rating_value(row["rating"]), current_sector),
                evidence=_reference_evidence(row, text),
                watch_items=_reference_watch_items(row["theme"], text, current_sector),
            )
        )
        if len(reviews) >= max_items:
            break
    return reviews


def _latest_previous_snapshot(reports_root: Path, trade_date: str) -> dict[str, Any] | None:
    if not reports_root.exists():
        return None
    date_dirs = [
        path
        for path in reports_root.iterdir()
        if path.is_dir() and TRADE_DATE_PATTERN.fullmatch(path.name) and path.name < trade_date
    ]
    for date_dir in sorted(date_dirs, key=lambda path: path.name, reverse=True):
        snapshot_path = _latest_snapshot_for_date(date_dir)
        if snapshot_path is None:
            continue
        try:
            return json.loads(snapshot_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
    return None


class _TextHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        normalized = " ".join(data.split())
        if normalized:
            self.parts.append(normalized)


def _html_text(html: str) -> str:
    parser = _TextHTMLParser()
    parser.feed(html)
    return "\n".join(parser.parts)


def _reference_sustainability_rows(text: str) -> list[dict[str, str]]:
    section = _section_after(text, "板块持续性排序", stop_markers=("资金轮动路径", "明日操作策略"))
    pattern = re.compile(
        r"(?P<rank>\d+)\n(?P<theme>[^\n]+)\n(?P<rating>高（6/1前）|中低|高|中|低)\n(?P<reason>[^\n]+)"
    )
    rows = []
    for match in pattern.finditer(section):
        rows.append(
            {
                "theme": _clean_theme(match.group("theme")),
                "rating": match.group("rating"),
                "reason": match.group("reason").strip(),
            }
        )
    return [row for row in rows if row["theme"]]


def _section_after(text: str, marker: str, stop_markers: tuple[str, ...]) -> str:
    start = text.find(marker)
    if start < 0:
        return ""
    end_candidates = [text.find(stop, start + len(marker)) for stop in stop_markers]
    end_candidates = [index for index in end_candidates if index >= 0]
    end = min(end_candidates) if end_candidates else len(text)
    return text[start:end]


def _clean_theme(theme: str) -> str:
    normalized = theme.strip()
    normalized = re.sub(r"\s+", "", normalized)
    return normalized


def _rating_value(label: str) -> str:
    if label.startswith("高"):
        return "high"
    if label.startswith("低"):
        return "low"
    return "medium"


def _reference_evidence(row: dict[str, str], text: str) -> list[str]:
    evidence = [f"上一复盘理由：{row['reason']}"]
    stocks = _reference_stocks_for_theme(row["theme"], text)
    if stocks:
        evidence.insert(0, f"上一复盘核心股：{'、'.join(stocks[:4])}")
    return evidence


def _reference_watch_items(
    theme: str,
    text: str,
    current_sector: SectorCandidate | None,
) -> list[str]:
    if current_sector is not None:
        return [f"观察{theme}前排承接是否继续强于板块平均"]
    stocks = _reference_stocks_for_theme(theme, text)
    if stocks:
        names = [stock.split("+", 1)[0].split("-", 1)[0].replace("跌超10%", "") for stock in stocks[:3]]
        return [f"观察{'、'.join(names)}能否重新转强"]
    return [f"观察{theme}是否重新回到强势前排"]


def _reference_stocks_for_theme(theme: str, text: str) -> list[str]:
    if "先进封装" in theme or "半导体设备" in theme:
        return _stocks_after_marker(text, "强势（先进封装方向）")
    if "存储" in theme:
        return _stocks_after_marker(text, "暴跌（存储 / 算力 / 光通信方向）")
    if "PCB" in theme:
        return _stocks_after_marker(text, "2. PCB概念")
    if "机器人" in theme:
        return _stocks_after_marker(text, "3. 人形机器人")
    return []


def _reference_stock_symbols_for_theme(theme: str, text: str) -> list[tuple[str, str]]:
    opportunity_section = _opportunity_section(text)
    if not opportunity_section:
        return []
    theme_names = _theme_stock_names(theme, text)
    rows = []
    pattern = re.compile(r"\n(?P<name>[\u4e00-\u9fa5A-Za-z]{2,8})\n(?P<code>\d{6})\n")
    for match in pattern.finditer(opportunity_section):
        name = match.group("name")
        if name in theme_names:
            rows.append((_normalize_symbol(match.group("code")), name))
    return rows


def _opportunity_section(text: str) -> str:
    section = _section_after(
        text,
        "明日可介入标的与仓位建议",
        stop_markers=("EIGHT", "八、", "操作纪律", "最终结论"),
    )
    if section:
        return section
    start = text.find("主攻A")
    if start < 0:
        return ""
    end = text.find("EIGHT", start)
    return text[start : end if end >= 0 else len(text)]


def _theme_stock_names(theme: str, text: str) -> set[str]:
    names = set()
    for stock in _reference_stocks_for_theme(theme, text):
        name = re.split(r"[+\-]|\d|涨超|跌超|跌停", stock, maxsplit=1)[0]
        if name:
            names.add(name)
    if "先进封装" in theme or "半导体设备" in theme:
        names.update({"长电科技", "华天科技", "北方华创"})
    if "机器人" in theme:
        names.update({"绿的谐波", "中大力德", "拓普集团"})
    if "PCB" in theme:
        names.update({"生益电子", "鹏鼎控股"})
    return names


def _normalize_symbol(code: str) -> str:
    if code.startswith(("60", "68", "90")):
        return f"{code}.SH"
    return f"{code}.SZ"


def _attach_current_stock_checks(
    reviews: list[HistoricalThemeReview],
    previous_review_html_path: Path | None,
    tickflow_provider: TickFlowQuoteProvider | None,
) -> list[HistoricalThemeReview]:
    if previous_review_html_path is None or tickflow_provider is None:
        return reviews
    try:
        text = _html_text(previous_review_html_path.read_text(encoding="utf-8"))
    except OSError:
        return reviews
    theme_symbols = {review.theme: _reference_stock_symbols_for_theme(review.theme, text) for review in reviews}
    symbols = _dedupe_symbols([symbol for pairs in theme_symbols.values() for symbol, _ in pairs])
    if not symbols:
        return reviews
    try:
        quotes = tickflow_provider.get_quotes(symbols)
    except Exception:
        return reviews
    quote_by_symbol = {quote.symbol: quote for quote in quotes}
    return [
        review.model_copy(
            update={
                "current_stock_checks": [
                    _quote_check_text(quote_by_symbol[symbol], fallback_name=name)
                    for symbol, name in theme_symbols.get(review.theme, [])[:4]
                    if symbol in quote_by_symbol and quote_by_symbol[symbol].pct_change is not None
                ]
            }
        )
        for review in reviews
    ]


def _dedupe_symbols(symbols: list[str]) -> list[str]:
    seen: set[str] = set()
    output = []
    for symbol in symbols:
        if symbol in seen:
            continue
        seen.add(symbol)
        output.append(symbol)
    return output


def _quote_check_text(quote: WatchlistQuote, fallback_name: str) -> str:
    name = quote.name or fallback_name
    pct_text = f"{quote.pct_change:+.2f}%" if quote.pct_change is not None else "无涨跌幅"
    turnover_text = _quote_turnover_text(quote.turnover_cny)
    turnover_part = f"，成交约{turnover_text}" if turnover_text else ""
    return f"{name} {quote.symbol} 今日{pct_text}{turnover_part}"


def _quote_turnover_text(turnover_cny: float | None) -> str:
    if not turnover_cny or turnover_cny <= 0:
        return ""
    if turnover_cny >= 100_000_000:
        return f"{turnover_cny / 100_000_000:.2f}亿"
    return f"{turnover_cny / 10_000:.0f}万"


def _stocks_after_marker(text: str, marker: str) -> list[str]:
    section = _section_after(
        text,
        marker,
        stop_markers=("板块逻辑分析", "持续性分析", "下个交易日看法", "3. 人形机器人", "4. 有色金属"),
    )
    pattern = re.compile(r"\n(?P<name>[\u4e00-\u9fa5A-Za-z]{2,8})\n(?P<pct>[+\-]?\d+(?:\.\d+)?%|涨超10%|跌超10%|跌停)")
    return [f"{match.group('name')}{match.group('pct')}" for match in pattern.finditer(section)]


def _matching_current_sector(theme: str, current_by_name: dict[str, SectorCandidate]) -> SectorCandidate | None:
    if theme in current_by_name:
        return current_by_name[theme]
    for name, sector in current_by_name.items():
        if name and (name in theme or theme in name):
            return sector
    return None


def _latest_snapshot_for_date(date_dir: Path) -> Path | None:
    for kind in ("close", "midday"):
        kind_dir = date_dir / kind
        if not kind_dir.exists():
            continue
        version_dirs = [
            path
            for path in kind_dir.iterdir()
            if path.is_dir() and VERSION_PATTERN.fullmatch(path.name) and (path / "snapshot.json").exists()
        ]
        if not version_dirs:
            continue
        latest = max(version_dirs, key=lambda path: int(VERSION_PATTERN.fullmatch(path.name).group(1)))  # type: ignore[union-attr]
        return latest / "snapshot.json"
    return None


def _build_historical_theme_reviews(
    snapshot: dict[str, Any],
    current_sectors: list[SectorCandidate],
    max_items: int,
) -> list[HistoricalThemeReview]:
    previous_report = snapshot.get("report") if isinstance(snapshot.get("report"), dict) else {}
    previous_sectors = {
        str(sector.get("name")): sector
        for sector in previous_report.get("sectors", [])
        if isinstance(sector, dict) and sector.get("name")
    }
    current_by_name = {sector.name: sector for sector in current_sectors}
    theme_rows = _previous_theme_rows(previous_report)
    reviews: list[HistoricalThemeReview] = []
    for row in theme_rows:
        theme = str(row.get("theme") or "").strip()
        if not theme or any(item.theme == theme for item in reviews):
            continue
        previous_rating = str(row.get("rating") or "")
        previous_sector = previous_sectors.get(theme, {})
        current_sector = current_by_name.get(theme)
        reviews.append(
            HistoricalThemeReview(
                theme=theme,
                previous_status=_previous_status(previous_rating),
                current_status=_current_status(current_sector),
                judgement=_judgement(previous_rating, current_sector),
                evidence=_historical_evidence(previous_sector),
                watch_items=_watch_items(theme, previous_sector, current_sector),
            )
        )
        if len(reviews) >= max_items:
            break
    return reviews


def _dedupe_reviews(reviews: list[HistoricalThemeReview]) -> list[HistoricalThemeReview]:
    seen: set[str] = set()
    output: list[HistoricalThemeReview] = []
    for review in reviews:
        key = review.theme
        if key in seen:
            continue
        seen.add(key)
        output.append(review)
    return output


def _previous_theme_rows(previous_report: dict[str, Any]) -> list[dict[str, str]]:
    structured = previous_report.get("structured_review") if isinstance(previous_report.get("structured_review"), dict) else {}
    rows: list[dict[str, str]] = []
    for item in structured.get("sustainability_ranking", []):
        if isinstance(item, dict) and item.get("sector"):
            rows.append({"theme": str(item["sector"]), "rating": str(item.get("rating") or "")})
    for item in structured.get("sector_reviews", []):
        if isinstance(item, dict) and item.get("sector"):
            rows.append({"theme": str(item["sector"]), "rating": str(item.get("sustainability") or "")})
    for item in previous_report.get("sectors", []):
        if isinstance(item, dict) and item.get("name"):
            rows.append({"theme": str(item["name"]), "rating": ""})
    return rows


def _previous_status(rating: str) -> str:
    labels = {"high": "高", "medium": "中", "low": "低"}
    return f"前一报告持续性{labels.get(rating, '待确认')}"


def _current_status(current_sector: SectorCandidate | None) -> str:
    if current_sector is None:
        return "今日未进入强势前排"
    return f"今日仍在强势前排，排名第{current_sector.rank}，涨跌幅{current_sector.pct_change:+.2f}%"


def _judgement(previous_rating: str, current_sector: SectorCandidate | None) -> str:
    if current_sector is not None and current_sector.score >= 70:
        return "延续确认"
    if current_sector is not None:
        return "分化观察"
    if previous_rating == "low":
        return "继续回避"
    return "降级观察"


def _historical_evidence(previous_sector: dict[str, Any]) -> list[str]:
    stocks = previous_sector.get("top_stocks", []) if isinstance(previous_sector, dict) else []
    stock_text = _stock_text(stocks)
    if stock_text:
        return [f"前一报告核心股：{stock_text}"]
    pct_change = previous_sector.get("pct_change") if isinstance(previous_sector, dict) else None
    if isinstance(pct_change, int | float):
        return [f"前一报告板块涨跌幅{pct_change:+.2f}%"]
    return ["前一报告列入持续性跟踪"]


def _watch_items(
    theme: str,
    previous_sector: dict[str, Any],
    current_sector: SectorCandidate | None,
) -> list[str]:
    if current_sector is not None:
        return [f"观察{theme}前排承接是否继续强于板块平均"]
    stock_names = _stock_names(previous_sector.get("top_stocks", []) if isinstance(previous_sector, dict) else [])
    if stock_names:
        return [f"观察{'、'.join(stock_names[:3])}能否重新转强"]
    return [f"观察{theme}是否重新回到强势前排"]


def _stock_text(stocks: Any) -> str:
    parts = []
    stock_rows = stocks if isinstance(stocks, list) else []
    for stock in stock_rows:
        if not isinstance(stock, dict) or not stock.get("name"):
            continue
        pct_change = stock.get("pct_change")
        suffix = f"{pct_change:+.2f}%" if isinstance(pct_change, int | float) else ""
        parts.append(f"{stock['name']}{suffix}")
    return "、".join(parts[:4])


def _stock_names(stocks: Any) -> list[str]:
    return [str(stock["name"]) for stock in stocks if isinstance(stock, dict) and stock.get("name")]
