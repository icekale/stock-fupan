from __future__ import annotations

from dataclasses import dataclass, field
from html import unescape
from html.parser import HTMLParser
import re
import time
from typing import Any, Literal

import httpx


ReviewSourceStatus = Literal["success", "failed", "disabled"]

KNOWN_THEME_KEYWORDS = (
    "有色金属",
    "PCB",
    "机器人",
    "贵金属",
    "工业金属",
    "半导体",
    "先进封装",
    "电力",
    "培育钻石",
    "黄金",
)

STOCK_NAME_PATTERN = re.compile(r"([\u4e00-\u9fa5A-Za-z]{2,8})(20CM)?涨停")


@dataclass(frozen=True)
class ReviewStockEvidence:
    name: str
    code: str | None = None
    pct_change: float | None = None
    note: str = ""
    source: str = ""


@dataclass(frozen=True)
class ReviewThemeEvidence:
    name: str
    pct_change: float | None = None
    reason: str = ""
    stocks: list[ReviewStockEvidence] = field(default_factory=list)
    source: str = ""


@dataclass(frozen=True)
class ReviewSourceResult:
    source: str
    source_url: str
    status: ReviewSourceStatus
    reason: str | None = None
    trade_date: str | None = None
    mainstream_views: list[str] = field(default_factory=list)
    themes: list[ReviewThemeEvidence] = field(default_factory=list)
    hot_stocks: list[ReviewStockEvidence] = field(default_factory=list)
    market_notes: list[str] = field(default_factory=list)
    board_efficiency: str | None = None


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


def _to_float(value: str | None) -> float | None:
    if value is None:
        return None
    cleaned = value.replace("%", "").replace("+", "").strip()
    try:
        return float(cleaned)
    except ValueError:
        return None


def _dedupe_names(names: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for name in names:
        normalized = name.strip(" ：:，,。\t\n")
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        output.append(normalized)
    return output


def _dedupe_texts(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        normalized = value.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        output.append(normalized)
    return output


def parse_10jqka_fupan_html(html: str, source_url: str) -> ReviewSourceResult:
    text = _html_text(html)
    mainstream_views = _extract_mainstream_views(text)
    market_notes = _extract_market_notes(text)
    board_efficiency = _extract_after_label(text, "封板效率")
    themes = _extract_10jqka_themes(text, mainstream_views)
    hot_stocks = _extract_10jqka_hot_stocks(text)
    has_content = bool(themes or hot_stocks or market_notes)
    return ReviewSourceResult(
        source="同花顺复盘",
        source_url=source_url,
        status="success" if has_content else "failed",
        reason=None if has_content else "未解析到复盘内容",
        mainstream_views=mainstream_views,
        themes=themes,
        hot_stocks=hot_stocks,
        market_notes=market_notes,
        board_efficiency=board_efficiency,
    )


def parse_eastmoney_ztfp_html(html: str, source_url: str) -> ReviewSourceResult:
    text = _html_text(html)
    titles = _extract_eastmoney_titles(text)
    themes = [
        ReviewThemeEvidence(name=keyword, source="东方财富涨停复盘")
        for keyword in KNOWN_THEME_KEYWORDS
        if keyword in text
    ]
    hot_stocks = [
        ReviewStockEvidence(
            name=name.strip(),
            pct_change=20.0 if marker else None,
            source="东方财富涨停复盘",
        )
        for name, marker in STOCK_NAME_PATTERN.findall(text)
        if _looks_like_stock_mention(name.strip())
    ]
    has_content = bool(themes or hot_stocks or titles)
    return ReviewSourceResult(
        source="东方财富涨停复盘",
        source_url=source_url,
        status="success" if has_content else "failed",
        reason=None if has_content else "未解析到涨停复盘内容",
        themes=_dedupe_themes(themes),
        hot_stocks=_dedupe_stocks(hot_stocks),
        market_notes=titles,
    )


def parse_eastmoney_ztfp_api_payload(
    payload: dict[str, Any], source_url: str, trade_date: str
) -> ReviewSourceResult:
    articles = _eastmoney_articles_for_trade_date(payload, trade_date)
    article_texts = [
        _join_title_summary(article.get("title"), article.get("summary")) for article in articles
    ]
    combined_text = "\n".join(article_texts)
    themes = [
        ReviewThemeEvidence(name=keyword, source="东方财富涨停复盘")
        for keyword in KNOWN_THEME_KEYWORDS
        if keyword in combined_text
    ]
    hot_stocks = [
        ReviewStockEvidence(
            name=name.strip(),
            pct_change=20.0 if marker else None,
            source="东方财富涨停复盘",
        )
        for name, marker in STOCK_NAME_PATTERN.findall(combined_text)
        if _looks_like_stock_mention(name.strip())
    ]
    for name, note_text in _extract_height_stocks(combined_text):
        hot_stocks.append(
            ReviewStockEvidence(
                name=name,
                note=note_text,
                source="东方财富涨停复盘",
            )
        )
    notes = _dedupe_texts(article_texts)
    has_content = bool(themes or hot_stocks or notes)
    return ReviewSourceResult(
        source="东方财富涨停复盘",
        source_url=source_url,
        status="success" if has_content else "failed",
        reason=None if has_content else "未解析到当日涨停复盘内容",
        trade_date=trade_date,
        themes=_dedupe_themes(themes),
        hot_stocks=_dedupe_stocks(hot_stocks),
        market_notes=notes,
    )


class ReviewSourceAggregator:
    def __init__(self, providers: list[object]) -> None:
        self.providers = providers

    def collect(self, trade_date: str) -> list[ReviewSourceResult]:
        results: list[ReviewSourceResult] = []
        for provider in self.providers:
            try:
                results.append(provider(trade_date))
            except Exception as exc:
                results.append(
                    ReviewSourceResult(
                        source=getattr(provider, "source_name", "review_source"),
                        source_url=getattr(provider, "source_url", ""),
                        status="failed",
                        reason=str(exc) or exc.__class__.__name__,
                    )
                )
        return results


class ThsFupanProvider:
    source_name = "同花顺复盘"

    def __init__(
        self,
        source_url: str = "https://stock.10jqka.com.cn/fupan/",
        timeout_seconds: float = 12,
        http_client: object | None = None,
    ) -> None:
        self.source_url = source_url
        self.timeout_seconds = timeout_seconds
        self._owns_client = http_client is None
        self.http_client = http_client or httpx.Client()

    def close(self) -> None:
        if self._owns_client:
            self.http_client.close()

    def __call__(self, trade_date: str) -> ReviewSourceResult:
        response = self.http_client.get(
            self.source_url,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        html = response.content.decode("gbk", errors="replace")
        return parse_10jqka_fupan_html(html, source_url=self.source_url)


class EastmoneyZtFpProvider:
    source_name = "东方财富涨停复盘"
    api_url = "https://np-listapi.eastmoney.com/comm/web/getNewsByColumns"

    def __init__(
        self,
        source_url: str = "https://stock.eastmoney.com/a/cztfp.html",
        timeout_seconds: float = 12,
        http_client: object | None = None,
    ) -> None:
        self.source_url = source_url
        self.timeout_seconds = timeout_seconds
        self._owns_client = http_client is None
        self.http_client = http_client or httpx.Client()

    def close(self) -> None:
        if self._owns_client:
            self.http_client.close()

    def __call__(self, trade_date: str) -> ReviewSourceResult:
        try:
            api_response = self.http_client.get(
                self.api_url,
                headers={"User-Agent": "Mozilla/5.0"},
                params={
                    "client": "web",
                    "biz": "web_news_col",
                    "column": "1201",
                    "order": "1",
                    "needInteractData": "0",
                    "page_index": "1",
                    "page_size": "20",
                    "req_trace": str(int(time.time() * 1000)),
                    "fields": "code,showTime,title,mediaName,summary,image,url,uniqueUrl,Np_dst",
                    "types": "1,20",
                },
                timeout=self.timeout_seconds,
            )
            api_response.raise_for_status()
            api_result = parse_eastmoney_ztfp_api_payload(
                api_response.json(),
                source_url=self.source_url,
                trade_date=trade_date,
            )
            if api_result.status == "success":
                return api_result
        except Exception:
            pass
        response = self.http_client.get(
            self.source_url,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        return parse_eastmoney_ztfp_html(response.text, source_url=self.source_url)


def _extract_mainstream_views(text: str) -> list[str]:
    match = re.search(r"主流看点\n([^\n]+)", text)
    if not match:
        return []
    return _dedupe_names([part.strip() for part in re.split(r"[、,/，]", match.group(1))])


def _extract_eastmoney_titles(text: str) -> list[str]:
    titles = []
    for line in text.splitlines():
        line = line.strip()
        if "涨停复盘" in line or ("概念" in line and "涨停" in line):
            titles.append(line)
    return _dedupe_names(titles)


def _eastmoney_articles_for_trade_date(
    payload: dict[str, Any], trade_date: str
) -> list[dict[str, Any]]:
    raw_items = payload.get("data", {}).get("list", [])
    if not isinstance(raw_items, list):
        return []
    articles: list[dict[str, Any]] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        show_time = str(item.get("showTime") or "")
        if not show_time.startswith(trade_date):
            continue
        title = str(item.get("title") or "")
        summary = str(item.get("summary") or "")
        if "涨停复盘" not in title and "涨停复盘" not in summary:
            continue
        articles.append(item)
    return articles


def _join_title_summary(title: object, summary: object) -> str:
    title_text = str(title or "").strip()
    summary_text = _clean_text(str(summary or ""))
    if title_text and summary_text:
        return f"{title_text}：{summary_text}"
    return title_text or summary_text


def _clean_text(value: str) -> str:
    value = re.sub(r"<[^>]+>", "", value)
    value = unescape(value)
    value = re.sub(r"^【[^】]+】", "", value).strip()
    return re.sub(r"\s+", " ", value).strip()


def _extract_market_notes(text: str) -> list[str]:
    notes: list[str] = []
    for label in ("权重股当日表现情况：", "个股活跃程度及脉络"):
        match = re.search(re.escape(label) + r"\n([^\n]+)", text)
        if match:
            notes.extend(_split_review_note(match.group(1)))
    return _dedupe_names(notes)


def _extract_after_label(text: str, label: str) -> str | None:
    match = re.search(re.escape(label) + r"\n([^\n]+)", text)
    return match.group(1).strip() if match else None


def _extract_10jqka_themes(text: str, mainstream_views: list[str]) -> list[ReviewThemeEvidence]:
    themes: list[ReviewThemeEvidence] = [
        ReviewThemeEvidence(name=name, source="同花顺复盘") for name in mainstream_views
    ]
    for name, _close, _change, pct in re.findall(
        r"([^\n\d%]{2,20})\s+\d{6}\n([\d.]+)\n([+-]?[\d.]+)\n([+-]?\d+(?:\.\d+)?)%",
        text,
    ):
        themes.append(
            ReviewThemeEvidence(
                name=name.strip(),
                pct_change=_to_float(pct),
                source="同花顺复盘",
            )
        )
    for name, pct in re.findall(r"([^\n%]{2,20})\n([+-]?\d+(?:\.\d+)?)%", text):
        clean_name = name.strip()
        if clean_name in {"深证成指", "中小综指", "创业板指", "上证指数"}:
            continue
        if _is_numeric_fragment(clean_name):
            continue
        if _looks_like_stock_name(clean_name) and clean_name not in mainstream_views:
            continue
        themes.append(
            ReviewThemeEvidence(name=clean_name, pct_change=_to_float(pct), source="同花顺复盘")
        )
    return _dedupe_themes(themes)


def _extract_10jqka_hot_stocks(text: str) -> list[ReviewStockEvidence]:
    stocks: list[ReviewStockEvidence] = []
    pattern = re.compile(r"([^\n\d%]{2,12})\s+(\d{6})\n[\d.]+\n[+-]?[\d.]+\n([+-]?\d+(?:\.\d+)?)%")
    for name, code, pct in pattern.findall(text):
        if code.startswith("88"):
            continue
        stocks.append(
            ReviewStockEvidence(
                name=name.strip(),
                code=code,
                pct_change=_to_float(pct),
                source="同花顺复盘",
            )
        )
    for name, pct in re.findall(r"([^\n\d%]{2,12})\n([+-]?\d+(?:\.\d+)?)%\n[\d.]+", text):
        clean_name = name.strip()
        if clean_name in {"深证成指", "中小综指", "创业板指"}:
            continue
        if _looks_like_stock_name(clean_name):
            stocks.append(
                ReviewStockEvidence(
                    name=clean_name,
                    pct_change=_to_float(pct),
                    source="同花顺复盘",
                )
            )
    return _dedupe_stocks(stocks)


def _split_review_note(note: str) -> list[str]:
    return [
        part.strip(" 。")
        for part in re.split(r"[。；;]", note)
        if part.strip(" 。")
    ]


def _is_numeric_fragment(value: str) -> bool:
    return bool(re.fullmatch(r"[+-]?\d+(?:\.\d+)?", value))


def _looks_like_stock_name(name: str) -> bool:
    return any(
        key in name
        for key in ("股份", "科技", "有色", "电子", "黄金", "矿业", "新能", "铝业", "铜箔")
    )


def _looks_like_stock_mention(name: str) -> bool:
    if not name or name in {"个股", "只股"}:
        return False
    if any(token in name for token in ("个股", "只股", "盘中一度触及")):
        return False
    return True


def _extract_height_stocks(text: str) -> list[tuple[str, str]]:
    matches: list[tuple[str, str]] = []
    for name, height in re.findall(r"([\u4e00-\u9fa5A-Za-z]{2,8})(\d+天\d+板)", text):
        matches.append((name, f"{name}{height}"))
    return matches


def _dedupe_themes(themes: list[ReviewThemeEvidence]) -> list[ReviewThemeEvidence]:
    by_name: dict[str, ReviewThemeEvidence] = {}
    output: list[ReviewThemeEvidence] = []
    for theme in themes:
        existing = by_name.get(theme.name)
        if existing is None:
            by_name[theme.name] = theme
            output.append(theme)
            continue
        if existing.pct_change is None and theme.pct_change is not None:
            by_name[theme.name] = theme
            output[output.index(existing)] = theme
    return output


def _dedupe_stocks(stocks: list[ReviewStockEvidence]) -> list[ReviewStockEvidence]:
    seen: set[tuple[str, str | None]] = set()
    output: list[ReviewStockEvidence] = []
    for stock in stocks:
        key = (stock.name, stock.code)
        if key in seen:
            continue
        seen.add(key)
        output.append(stock)
    return output
