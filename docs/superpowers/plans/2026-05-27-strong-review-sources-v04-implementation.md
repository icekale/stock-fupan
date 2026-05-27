# Strong Review Sources v0.4 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a real strong-theme review engine that identifies the day’s strongest A-share sectors/stocks, using TickFlow for market strength and only 同花顺 + 东方财富 as curated review information sources.

**Architecture:** Add a focused `review_sources` provider layer that returns normalized strong-theme evidence from 同花顺复盘 and 东方财富涨停复盘. Merge that evidence with TickFlow-ranked market strength before scoring/report generation, so the HTML report discusses only confirmed strong themes and front-row stocks, with no fake or generic fallback content.

**Tech Stack:** Python 3.12, FastAPI service layer, Pydantic DTOs, httpx, html.parser/regex fixture parsers, pytest, Jinja2 HTML templates.

---

## Source Boundary

- 同花顺复盘 `https://stock.10jqka.com.cn/fupan/` is a curated review source.
- 东方财富涨停复盘 `https://stock.eastmoney.com/a/cztfp.html` is a curated review source.
- TickFlow remains market data / quote strength only, not a review source.
- Anspire remains sector news/catalyst search only, not a review source.
- AkShare/MCP is not part of v0.4 review source scope unless added later by explicit request.
- Production report output must not fabricate unavailable review source content.

## File Structure

- Create `apps/api/app/providers/review_sources.py`: normalized DTOs, 同花顺 parser/provider, 东方财富 parser/provider skeleton, aggregator.
- Create `apps/api/tests/fixtures/10jqka_fupan_sample.html`: compact HTML fixture copied from the real 同花顺 page structure.
- Create `apps/api/tests/fixtures/eastmoney_ztfp_sample.html`: compact HTML/list fixture for 东方财富 article/list parsing.
- Create `apps/api/tests/test_review_sources.py`: parser and aggregator behavior tests.
- Modify `apps/api/app/schemas/report.py`: add review evidence fields to sector and stock candidates.
- Modify `apps/api/app/providers/factory.py`: create and expose `review_source_provider`.
- Modify `apps/api/app/config.py`: add review source settings with defaults enabled for 同花顺 and 东方财富.
- Modify `apps/api/app/services/report_generator.py`: fetch review evidence, merge into scored sectors, persist source status.
- Modify `apps/api/app/services/structured_review_builder.py`: generate strong-theme language from evidence/front-row stocks instead of generic sector wording.
- Modify `apps/api/app/renderers/templates/mobile_report.html.j2`: show source attribution, front-row stock tables, weak branches, next-day conditions.
- Modify `apps/api/tests/test_report_api.py` and `apps/api/tests/test_structured_review.py`: assert strong-theme outputs and no generic/fake weak-source text.

---

### Task 1: Review Source DTOs and 同花顺 Parser

**Files:**
- Create: `apps/api/app/providers/review_sources.py`
- Create: `apps/api/tests/fixtures/10jqka_fupan_sample.html`
- Test: `apps/api/tests/test_review_sources.py`

- [ ] **Step 1: Write the failing test**

Create `apps/api/tests/fixtures/10jqka_fupan_sample.html`:

```html
<!doctype html>
<html><head><meta charset="gbk"><title>复盘_股票_同花顺财经</title></head><body>
<div id="fpzj"><div id="block_1887">A股三大指数今日涨跌不一，全市场超4000只个股下跌。</div></div>
<div id="fp_item_3">
  <h2>指数/概念分析</h2>
  <ul class="rise_top3">
    <li><span class="stock_name">金属铅</span> +2.50%(50.35)</li>
    <li><span class="stock_name">金属锌</span> +2.12%(48.84)</li>
    <li><span class="stock_name">黄金概念</span> +1.56%(60.02)</li>
  </ul>
  <div id="block_1889">贵金属、有色金属板块低开高走，招金黄金早盘涨停，西部黄金、赤峰黄金、紫金矿业涨幅居前。PCB概念股午后多数上扬，生益电子20cm涨停，宝鼎科技、生益科技涨停，沪电股份涨超9%。</div>
  <div class="rise_top3_tipbox" id="tab_308864">
    <strong class="strong_s">金属铅</strong>
    <table><tbody>
      <tr class="c_rise"><td>华锡有色</td><td>10.009%</td><td>61.22</td></tr>
      <tr class="c_rise"><td>盛龙股份</td><td>10.009%</td><td>25.83</td></tr>
    </tbody></table>
  </div>
</div>
<div id="fp_item_4">
  <strong>主流看点</strong>
  <div id="block_1890">贵金属、PCB、培育钻石</div>
  <strong>个股活跃程度及脉络</strong>
  <div id="block_1891">盘面上，贵金属、有色金属板块低开高走，招金黄金早盘涨停，PCB概念股午后多数上扬，生益电子20cm涨停。</div>
  <strong>封板效率</strong>
  <div id="block_1892">一般</div>
</div>
<div id="fp_item_6">
  <strong class="mod_hd_s mt30">热门板块：</strong>
  <ul class="chart_switch_cnt">
    <li class="appendChart" codename="贵金属"><a>贵金属 881169</a><strong class="fr chart_switch_value rise"><span>5624.89</span><span>+222.22</span><span>+4.11%</span></strong></li>
    <li class="appendChart" codename="工业金属"><a>工业金属 881168</a><strong class="fr chart_switch_value rise"><span>4829.67</span><span>+89.06</span><span>+1.88%</span></strong></li>
  </ul>
  <strong class="mod_hd_s mt30">热门个股：</strong>
  <ul class="chart_switch_cnt">
    <li class="appendChart" codename="肯特股份"><a>肯特股份 301591</a><strong class="fr chart_switch_value rise"><span>58.68</span><span>+9.78</span><span>+20.00%</span></strong></li>
    <li class="appendChart" codename="生益电子"><a>生益电子 688183</a><strong class="fr chart_switch_value rise"><span>132.10</span><span>+22.02</span><span>+20.00%</span></strong></li>
  </ul>
</div>
</body></html>
```

Create `apps/api/tests/test_review_sources.py`:

```python
from pathlib import Path

from app.providers.review_sources import parse_10jqka_fupan_html


FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_10jqka_fupan_extracts_mainstream_views_hot_themes_and_front_row_stocks() -> None:
    html = (FIXTURES / "10jqka_fupan_sample.html").read_text(encoding="utf-8")

    result = parse_10jqka_fupan_html(html, source_url="https://stock.10jqka.com.cn/fupan/")

    assert result.source == "同花顺复盘"
    assert result.status == "success"
    assert result.trade_date is None
    assert result.mainstream_views == ["贵金属", "PCB", "培育钻石"]
    assert [theme.name for theme in result.themes[:3]] == ["贵金属", "PCB", "培育钻石"]
    assert any(theme.name == "金属铅" and theme.pct_change == 2.50 for theme in result.themes)
    assert any(theme.name == "贵金属" and theme.pct_change == 4.11 for theme in result.themes)
    assert any(stock.name == "生益电子" and stock.code == "688183" and stock.pct_change == 20.0 for stock in result.hot_stocks)
    assert any("PCB概念股午后多数上扬" in note for note in result.market_notes)
    assert result.board_efficiency == "一般"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd apps/api && .venv/bin/python -m pytest tests/test_review_sources.py::test_parse_10jqka_fupan_extracts_mainstream_views_hot_themes_and_front_row_stocks -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'app.providers.review_sources'`.

- [ ] **Step 3: Write minimal implementation**

Create `apps/api/app/providers/review_sources.py` with:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from html.parser import HTMLParser
import re
from typing import Literal


ReviewSourceStatus = Literal["success", "failed", "disabled"]


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


def parse_10jqka_fupan_html(html: str, source_url: str) -> ReviewSourceResult:
    text = _html_text(html)
    mainstream_views = _extract_mainstream_views(text)
    market_notes = _extract_market_notes(text)
    board_efficiency = _extract_after_label(text, "封板效率")
    themes = _extract_10jqka_themes(text, mainstream_views)
    hot_stocks = _extract_10jqka_hot_stocks(text)
    return ReviewSourceResult(
        source="同花顺复盘",
        source_url=source_url,
        status="success" if themes or hot_stocks or market_notes else "failed",
        reason=None if themes or hot_stocks or market_notes else "未解析到复盘内容",
        mainstream_views=mainstream_views,
        themes=themes,
        hot_stocks=hot_stocks,
        market_notes=market_notes,
        board_efficiency=board_efficiency,
    )


def _extract_mainstream_views(text: str) -> list[str]:
    match = re.search(r"主流看点\n([^\n]+)", text)
    if not match:
        return []
    return _dedupe_names([part.strip() for part in re.split(r"[、,/，]", match.group(1))])


def _extract_market_notes(text: str) -> list[str]:
    notes: list[str] = []
    for label in ("权重股当日表现情况：", "个股活跃程度及脉络"):
        match = re.search(re.escape(label) + r"\n([^\n]+)", text)
        if match:
            notes.append(match.group(1).strip())
    return _dedupe_names(notes)


def _extract_after_label(text: str, label: str) -> str | None:
    match = re.search(re.escape(label) + r"\n([^\n]+)", text)
    return match.group(1).strip() if match else None


def _extract_10jqka_themes(text: str, mainstream_views: list[str]) -> list[ReviewThemeEvidence]:
    themes: list[ReviewThemeEvidence] = [
        ReviewThemeEvidence(name=name, source="同花顺复盘") for name in mainstream_views
    ]
    for name, pct in re.findall(r"([^\n%]{2,20})\n([+-]?\d+(?:\.\d+)?)%", text):
        clean_name = name.strip()
        if clean_name in {"深证成指", "中小综指", "创业板指", "上证指数"}:
            continue
        if any(stock_word in clean_name for stock_word in ("科技", "股份", "有色", "黄金", "矿业", "电子")) and clean_name not in mainstream_views:
            continue
        themes.append(
            ReviewThemeEvidence(name=clean_name, pct_change=_to_float(pct), source="同花顺复盘")
        )
    return _dedupe_themes(themes)


def _extract_10jqka_hot_stocks(text: str) -> list[ReviewStockEvidence]:
    stocks: list[ReviewStockEvidence] = []
    pattern = re.compile(r"([^\n\d%]{2,12})\s+(\d{6})\n[\d.]+\n[+-]?[\d.]+\n([+-]?\d+(?:\.\d+)?)%")
    for name, code, pct in pattern.findall(text):
        stocks.append(
            ReviewStockEvidence(
                name=name.strip(),
                code=code,
                pct_change=_to_float(pct),
                source="同花顺复盘",
            )
        )
    for name, pct in re.findall(r"([^\n\d%]{2,12})\n([+-]?\d+(?:\.\d+)?)%\n[\d.]+", text):
        if name in {"深证成指", "中小综指", "创业板指"}:
            continue
        if any(key in name for key in ("股份", "科技", "有色", "电子", "黄金", "矿业", "新能")):
            stocks.append(
                ReviewStockEvidence(name=name.strip(), pct_change=_to_float(pct), source="同花顺复盘")
            )
    return _dedupe_stocks(stocks)


def _dedupe_themes(themes: list[ReviewThemeEvidence]) -> list[ReviewThemeEvidence]:
    seen: set[str] = set()
    output: list[ReviewThemeEvidence] = []
    for theme in themes:
        if theme.name in seen:
            continue
        seen.add(theme.name)
        output.append(theme)
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
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
cd apps/api && .venv/bin/python -m pytest tests/test_review_sources.py::test_parse_10jqka_fupan_extracts_mainstream_views_hot_themes_and_front_row_stocks -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/providers/review_sources.py apps/api/tests/fixtures/10jqka_fupan_sample.html apps/api/tests/test_review_sources.py
git commit -m "feat: parse ths fupan review source"
```

---

### Task 2: 东方财富涨停复盘 Parser and Source Aggregator

**Files:**
- Modify: `apps/api/app/providers/review_sources.py`
- Create: `apps/api/tests/fixtures/eastmoney_ztfp_sample.html`
- Test: `apps/api/tests/test_review_sources.py`

- [ ] **Step 1: Write the failing tests**

Append fixture `apps/api/tests/fixtures/eastmoney_ztfp_sample.html`:

```html
<ul id="newsListContent">
  <li><a href="https://finance.eastmoney.com/a/202605263409000000.html" title="涨停复盘：有色金属、PCB概念股集体爆发 生益电子20CM涨停">涨停复盘：有色金属、PCB概念股集体爆发 生益电子20CM涨停</a><span>05-26 16:25</span></li>
  <li><a href="https://finance.eastmoney.com/a/202605263409000001.html" title="机器人概念午后走强 中大力德涨停">机器人概念午后走强 中大力德涨停</a><span>05-26 15:30</span></li>
</ul>
```

Append tests to `apps/api/tests/test_review_sources.py`:

```python
from app.providers.review_sources import (
    ReviewSourceAggregator,
    ReviewSourceResult,
    parse_eastmoney_ztfp_html,
)


def test_parse_eastmoney_ztfp_extracts_limit_up_themes_and_stock_mentions() -> None:
    html = (FIXTURES / "eastmoney_ztfp_sample.html").read_text(encoding="utf-8")

    result = parse_eastmoney_ztfp_html(html, source_url="https://stock.eastmoney.com/a/cztfp.html")

    assert result.source == "东方财富涨停复盘"
    assert result.status == "success"
    assert [theme.name for theme in result.themes] == ["有色金属", "PCB", "机器人"]
    assert any(stock.name == "生益电子" and stock.pct_change == 20.0 for stock in result.hot_stocks)
    assert any(stock.name == "中大力德" for stock in result.hot_stocks)
    assert result.market_notes[0].startswith("涨停复盘：有色金属")


def test_review_source_aggregator_returns_status_for_failed_source() -> None:
    aggregator = ReviewSourceAggregator(
        providers=[
            lambda trade_date: ReviewSourceResult(
                source="同花顺复盘",
                source_url="https://stock.10jqka.com.cn/fupan/",
                status="success",
                themes=[],
                hot_stocks=[],
            ),
            lambda trade_date: (_ for _ in ()).throw(RuntimeError("blocked")),
        ]
    )

    results = aggregator.collect("2026-05-26")

    assert len(results) == 2
    assert results[0].source == "同花顺复盘"
    assert results[0].status == "success"
    assert results[1].source == "review_source"
    assert results[1].status == "failed"
    assert results[1].reason == "blocked"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
cd apps/api && .venv/bin/python -m pytest tests/test_review_sources.py -v
```

Expected: FAIL for missing `parse_eastmoney_ztfp_html` and `ReviewSourceAggregator`.

- [ ] **Step 3: Write minimal implementation**

Append to `apps/api/app/providers/review_sources.py`:

```python
KNOWN_THEME_KEYWORDS = (
    "有色金属",
    "贵金属",
    "工业金属",
    "PCB",
    "机器人",
    "半导体",
    "先进封装",
    "电力",
    "培育钻石",
    "黄金",
)

STOCK_NAME_PATTERN = re.compile(r"([\u4e00-\u9fa5A-Za-z]{2,8})(?:20CM)?涨停")


def parse_eastmoney_ztfp_html(html: str, source_url: str) -> ReviewSourceResult:
    text = _html_text(html)
    titles = _dedupe_names(re.findall(r"涨停复盘[^\n]+|[^\n]+概念[^\n]+涨停", text))
    themes = []
    for keyword in KNOWN_THEME_KEYWORDS:
        if keyword in text:
            themes.append(ReviewThemeEvidence(name=keyword, source="东方财富涨停复盘"))
    hot_stocks = []
    for stock_name in STOCK_NAME_PATTERN.findall(text):
        pct = 20.0 if "20CM" in text[max(0, text.find(stock_name) - 20): text.find(stock_name) + 20] else None
        hot_stocks.append(
            ReviewStockEvidence(
                name=stock_name,
                pct_change=pct,
                source="东方财富涨停复盘",
            )
        )
    return ReviewSourceResult(
        source="东方财富涨停复盘",
        source_url=source_url,
        status="success" if themes or hot_stocks or titles else "failed",
        reason=None if themes or hot_stocks or titles else "未解析到涨停复盘内容",
        themes=_dedupe_themes(themes),
        hot_stocks=_dedupe_stocks(hot_stocks),
        market_notes=titles,
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
cd apps/api && .venv/bin/python -m pytest tests/test_review_sources.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/providers/review_sources.py apps/api/tests/fixtures/eastmoney_ztfp_sample.html apps/api/tests/test_review_sources.py
git commit -m "feat: parse eastmoney limit-up review source"
```

---

### Task 3: HTTP Providers for 同花顺 and 东方财富

**Files:**
- Modify: `apps/api/app/providers/review_sources.py`
- Modify: `apps/api/app/config.py`
- Modify: `apps/api/app/providers/factory.py`
- Test: `apps/api/tests/test_review_sources.py`

- [ ] **Step 1: Write failing provider tests**

Append to `apps/api/tests/test_review_sources.py`:

```python
from app.config import Settings
from app.providers.factory import create_provider_bundle
from app.providers.review_sources import EastmoneyZtFpProvider, ThsFupanProvider


class FakeResponse:
    def __init__(self, text: str, content: bytes | None = None) -> None:
        self.text = text
        self.content = content if content is not None else text.encode("utf-8")

    def raise_for_status(self) -> None:
        return None


class FakeHttpClient:
    def __init__(self, response: FakeResponse) -> None:
        self.response = response
        self.requests = []

    def get(self, url: str, **kwargs: object) -> FakeResponse:
        self.requests.append((url, kwargs))
        return self.response


def test_ths_provider_fetches_gbk_page_and_parses_review() -> None:
    html = (FIXTURES / "10jqka_fupan_sample.html").read_text(encoding="utf-8")
    client = FakeHttpClient(FakeResponse("", content=html.encode("gbk")))
    provider = ThsFupanProvider(http_client=client)

    result = provider("2026-05-26")

    assert result.source == "同花顺复盘"
    assert result.status == "success"
    assert "https://stock.10jqka.com.cn/fupan/" in client.requests[0][0]
    assert any(theme.name == "贵金属" for theme in result.themes)


def test_eastmoney_provider_fetches_page_and_parses_review() -> None:
    html = (FIXTURES / "eastmoney_ztfp_sample.html").read_text(encoding="utf-8")
    client = FakeHttpClient(FakeResponse(html))
    provider = EastmoneyZtFpProvider(http_client=client)

    result = provider("2026-05-26")

    assert result.source == "东方财富涨停复盘"
    assert result.status == "success"
    assert "https://stock.eastmoney.com/a/cztfp.html" in client.requests[0][0]
    assert any(theme.name == "PCB" for theme in result.themes)


def test_provider_bundle_includes_enabled_review_sources() -> None:
    settings = Settings(review_sources_enabled=True)

    bundle = create_provider_bundle(settings)

    assert bundle.review_source_provider is not None
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
cd apps/api && .venv/bin/python -m pytest tests/test_review_sources.py::test_ths_provider_fetches_gbk_page_and_parses_review tests/test_review_sources.py::test_eastmoney_provider_fetches_page_and_parses_review tests/test_review_sources.py::test_provider_bundle_includes_enabled_review_sources -v
```

Expected: FAIL for missing providers/settings/bundle field.

- [ ] **Step 3: Implement providers and settings**

Add to `apps/api/app/config.py` inside `Settings`:

```python
    review_sources_enabled: bool = True
    ths_fupan_url: str = "https://stock.10jqka.com.cn/fupan/"
    eastmoney_ztfp_url: str = "https://stock.eastmoney.com/a/cztfp.html"
```

Add to `apps/api/app/providers/review_sources.py`:

```python
import httpx


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
        response = self.http_client.get(
            self.source_url,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        return parse_eastmoney_ztfp_html(response.text, source_url=self.source_url)
```

Modify `apps/api/app/providers/factory.py`:

```python
from app.providers.review_sources import (
    EastmoneyZtFpProvider,
    ReviewSourceAggregator,
    ThsFupanProvider,
)
```

Add `review_source_provider` to `ProviderBundle`:

```python
    review_source_provider: ReviewSourceAggregator | None = None
```

Add close call:

```python
        if self.review_source_provider is not None:
            _close_provider(self.review_source_provider)
```

Pass it in `create_provider_bundle`:

```python
        review_source_provider=_create_review_source_provider(settings),
```

Add helper:

```python
def _create_review_source_provider(settings: Settings) -> ReviewSourceAggregator | None:
    if not settings.review_sources_enabled:
        return None
    return ReviewSourceAggregator(
        providers=[
            ThsFupanProvider(
                source_url=settings.ths_fupan_url,
                timeout_seconds=settings.provider_timeout_seconds,
            ),
            EastmoneyZtFpProvider(
                source_url=settings.eastmoney_ztfp_url,
                timeout_seconds=settings.provider_timeout_seconds,
            ),
        ]
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
cd apps/api && .venv/bin/python -m pytest tests/test_review_sources.py tests/test_real_providers.py::test_provider_factory_can_force_fake_providers -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/providers/review_sources.py apps/api/app/config.py apps/api/app/providers/factory.py apps/api/tests/test_review_sources.py
git commit -m "feat: add curated review source providers"
```

---

### Task 4: Merge Review Evidence into Strong Theme Reports

**Files:**
- Modify: `apps/api/app/schemas/report.py`
- Modify: `apps/api/app/services/report_generator.py`
- Test: `apps/api/tests/test_report_api.py`

- [ ] **Step 1: Write failing report merge test**

Append to `apps/api/tests/test_report_api.py`:

```python
from app.providers.review_sources import ReviewSourceResult, ReviewStockEvidence, ReviewThemeEvidence


class FakeReviewSourceProvider:
    def collect(self, trade_date: str) -> list[ReviewSourceResult]:
        return [
            ReviewSourceResult(
                source="同花顺复盘",
                source_url="https://stock.10jqka.com.cn/fupan/",
                status="success",
                mainstream_views=["贵金属", "PCB"],
                themes=[
                    ReviewThemeEvidence(name="PCB", pct_change=4.2, reason="前排加速", source="同花顺复盘"),
                    ReviewThemeEvidence(name="贵金属", pct_change=4.1, reason="低开高走", source="同花顺复盘"),
                ],
                hot_stocks=[
                    ReviewStockEvidence(name="生益电子", code="688183", pct_change=20.0, source="同花顺复盘"),
                    ReviewStockEvidence(name="宝鼎科技", code="002552", pct_change=10.0, source="同花顺复盘"),
                ],
                market_notes=["PCB概念股午后多数上扬，生益电子20cm涨停。"],
            ),
            ReviewSourceResult(
                source="东方财富涨停复盘",
                source_url="https://stock.eastmoney.com/a/cztfp.html",
                status="success",
                themes=[ReviewThemeEvidence(name="PCB", source="东方财富涨停复盘")],
                hot_stocks=[ReviewStockEvidence(name="生益电子", pct_change=20.0, source="东方财富涨停复盘")],
                market_notes=["涨停复盘：PCB概念股集体爆发 生益电子20CM涨停"],
            ),
        ]


def test_report_generator_merges_curated_review_sources_into_strong_theme(tmp_path: Path) -> None:
    generator = ReportGenerator(
        reports_root=tmp_path,
        market_provider=FakeMarketDataProvider(),
        news_provider=FakeNewsProvider(),
        llm_provider=FakeLLMProvider(),
        review_source_provider=FakeReviewSourceProvider(),
    )

    result = generator.generate_close_report("2026-05-26")

    pcb = next(sector for sector in result.report.sectors if sector.name == "PCB")
    assert "同花顺复盘" in pcb.review_sources
    assert "东方财富涨停复盘" in pcb.review_sources
    assert any(stock.name == "生益电子" for stock in pcb.top_stocks)
    assert any("PCB概念股午后多数上扬" in note for note in pcb.review_notes)
    assert result.provider_status["review_sources"][0]["source"] == "同花顺复盘"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd apps/api && .venv/bin/python -m pytest tests/test_report_api.py::test_report_generator_merges_curated_review_sources_into_strong_theme -v
```

Expected: FAIL because `ReportGenerator` has no `review_source_provider` parameter or sector fields.

- [ ] **Step 3: Implement schema and generator merge**

Modify `apps/api/app/schemas/report.py`:

```python
class SectorCandidate(BaseModel):
    name: str
    score: float
    rank: int
    pct_change: float
    reason: str
    top_stocks: list[StockCandidate] = Field(default_factory=list)
    news_summaries: list[str] = Field(default_factory=list)
    factor_scores: dict[str, float] = Field(default_factory=dict)
    confidence: str = "medium"
    review_sources: list[str] = Field(default_factory=list)
    review_notes: list[str] = Field(default_factory=list)
```

Modify `ReportGenerator.__init__` in `apps/api/app/services/report_generator.py`:

```python
        review_source_provider: object | None = None,
```

Set:

```python
        self.review_source_provider = review_source_provider
```

In `generate_close_report`, after `scored_sectors = ...` add:

```python
        review_source_results = []
        if self.review_source_provider is not None:
            review_source_results = self.review_source_provider.collect(trade_date)
```

When building `SectorCandidate`, replace the list comprehension with a helper:

```python
        sector_candidates = [
            self._build_sector_candidate(scored, news_items, review_source_results)
            for scored in scored_sectors
        ]
```

Add methods to `ReportGenerator`:

```python
    def _build_sector_candidate(self, scored, news_items, review_source_results) -> SectorCandidate:
        review_sources = []
        review_notes = []
        top_stocks = []
        sector_key = scored.name.lower()
        for result in review_source_results:
            for theme in result.themes:
                if _theme_matches(sector_key, theme.name):
                    review_sources.append(result.source)
                    if theme.reason:
                        review_notes.append(theme.reason)
            for note in result.market_notes:
                if scored.name in note or any(theme.name in note for theme in result.themes if _theme_matches(sector_key, theme.name)):
                    review_notes.append(note)
            for stock in result.hot_stocks:
                if scored.name in stock.note or scored.name in " ".join(result.mainstream_views) or scored.name in " ".join(note for note in result.market_notes):
                    top_stocks.append(
                        StockCandidate(
                            code=stock.code or "",
                            name=stock.name,
                            pct_change=stock.pct_change or 0.0,
                            tags=[stock.source] if stock.source else [],
                        )
                    )
        return SectorCandidate(
            name=scored.name,
            score=scored.score,
            rank=scored.rank,
            pct_change=scored.pct_change,
            reason="强度与复盘源共同确认" if review_sources else "综合评分靠前",
            top_stocks=_dedupe_stock_candidates(top_stocks),
            news_summaries=[item.summary for item in news_items if item.matched_sector == scored.name],
            factor_scores=scored.factor_scores,
            review_sources=_dedupe_strings(review_sources),
            review_notes=_dedupe_strings(review_notes),
        )


def _theme_matches(sector_key: str, theme_name: str) -> bool:
    theme_key = theme_name.lower()
    aliases = {
        "pcb": ["pcb"],
        "有色金属": ["有色", "贵金属", "工业金属", "小金属", "黄金", "金属"],
        "半导体": ["半导体", "芯片", "先进封装", "封测"],
    }
    candidates = aliases.get(sector_key, [sector_key])
    return any(candidate in theme_key or theme_key in candidate for candidate in candidates)


def _dedupe_strings(values: list[str]) -> list[str]:
    seen = set()
    output = []
    for value in values:
        normalized = value.strip()
        if normalized and normalized not in seen:
            seen.add(normalized)
            output.append(normalized)
    return output


def _dedupe_stock_candidates(stocks: list[StockCandidate]) -> list[StockCandidate]:
    seen = set()
    output = []
    for stock in stocks:
        key = (stock.code, stock.name)
        if key in seen:
            continue
        seen.add(key)
        output.append(stock)
    return output[:8]
```

Add `StockCandidate` import.

Add status payload:

```python
            "review_sources": [result.__dict__ for result in review_source_results],
```

- [ ] **Step 4: Wire factory into main app**

Where `ReportGenerator` is constructed, pass:

```python
review_source_provider=bundle.review_source_provider,
```

- [ ] **Step 5: Run test to verify it passes**

Run:

```bash
cd apps/api && .venv/bin/python -m pytest tests/test_report_api.py::test_report_generator_merges_curated_review_sources_into_strong_theme -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add apps/api/app/schemas/report.py apps/api/app/services/report_generator.py apps/api/app/main.py apps/api/tests/test_report_api.py
git commit -m "feat: merge curated review evidence into sectors"
```

---

### Task 5: Strong-Theme Structured Review Language and HTML Tables

**Files:**
- Modify: `apps/api/app/services/structured_review_builder.py`
- Modify: `apps/api/app/renderers/templates/mobile_report.html.j2`
- Test: `apps/api/tests/test_structured_review.py`

- [ ] **Step 1: Write failing structured output test**

Append to `apps/api/tests/test_structured_review.py`:

```python
from app.schemas.report import StockCandidate


def test_structured_review_uses_front_row_stocks_and_review_sources_in_sector_analysis() -> None:
    report = _sample_report()
    report.sectors[0].name = "PCB"
    report.sectors[0].top_stocks = [
        StockCandidate(code="688183", name="生益电子", pct_change=20.0, tags=["同花顺复盘"]),
        StockCandidate(code="002552", name="宝鼎科技", pct_change=10.0, tags=["东方财富涨停复盘"]),
    ]
    report.sectors[0].review_sources = ["同花顺复盘", "东方财富涨停复盘"]
    report.sectors[0].review_notes = ["PCB概念股午后多数上扬，生益电子20cm涨停。"]

    review = build_structured_review(report)

    sector = review.sector_reviews[0]
    assert "生益电子" in "\n".join(sector.strengths)
    assert "同花顺复盘" in "\n".join(sector.logic_points)
    assert "前排" in sector.next_day_view
    assert review.practical_conclusion.headline.startswith("明日最实战")
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd apps/api && .venv/bin/python -m pytest tests/test_structured_review.py::test_structured_review_uses_front_row_stocks_and_review_sources_in_sector_analysis -v
```

Expected: FAIL because builder ignores `top_stocks` and `review_sources`.

- [ ] **Step 3: Update builder language**

Modify `_build_sector_review` in `apps/api/app/services/structured_review_builder.py`:

```python
def _build_sector_review(sector: SectorCandidate) -> StructuredSectorReview:
    rating = _rating_for_sector(sector)
    news_evidence = _compact_news_evidence(sector.news_summaries)
    front_row_text = _front_row_stock_text(sector)
    review_source_text = "、".join(sector.review_sources) if sector.review_sources else "复盘源暂未确认"
    review_note = _compact_news_evidence(sector.review_notes, max_length=96)
    return StructuredSectorReview(
        sector=sector.name,
        headline=f"{sector.name}：{_headline_suffix(rating)}",
        stage=_stage_for_rating(rating),
        strengths=[
            f"涨跌幅{sector.pct_change:+.2f}%",
            f"综合评分{sector.score:.1f}",
            front_row_text or "前排个股仍待复盘源确认",
            review_note or news_evidence or sector.reason,
        ],
        weaknesses=["后排跟风股承接要求更高", "若前排放量开板，板块容易分化"],
        logic=f"{sector.name}的判断优先看前排股强度，其次看同花顺/东方财富复盘源是否共同确认。",
        logic_points=[
            f"价格强度：板块涨跌幅{sector.pct_change:+.2f}%。",
            f"评分结构：综合评分{sector.score:.1f}，排名第{sector.rank}。",
            f"复盘源确认：{review_source_text}。",
            f"前排个股：{front_row_text or '暂未解析到明确前排股'}。",
        ],
        sustainability_analysis=_sustainability_analysis(sector, rating),
        sustainability=rating,
        next_day_view=f"观察{sector.name}前排股分歧后的承接，优先看{front_row_text or '核心股'}，不追后排补涨。",
        watch_items=[f"{sector.name}前排股竞价和开盘承接", "板块内强弱切换是否温和"],
        avoid_items=["缩量冲高回落", "无复盘源确认的低位跟风"],
    )


def _front_row_stock_text(sector: SectorCandidate) -> str:
    stocks = [stock for stock in sector.top_stocks if stock.name]
    return "、".join(f"{stock.name}{stock.pct_change:+.2f}%" for stock in stocks[:4])
```

Update `_rating_for_sector`:

```python
    if sector.score >= 70 and (sector.news_summaries or sector.review_sources):
```

- [ ] **Step 4: Update HTML template with front-row stock table and sources**

Inside sector card in `mobile_report.html.j2`, after `<p><strong>当前阶段：</strong>{{ sector.stage }}</p>` add:

```jinja2
                {% set candidate = report.sectors[loop.index0] %}
                {% if candidate.review_sources %}
                  <p class="muted">复盘源：{{ candidate.review_sources|join("、") }}</p>
                {% endif %}
                {% if candidate.top_stocks %}
                  <table aria-label="前排强势个股">
                    <tr><th>前排个股</th><th>涨跌幅</th><th>来源</th></tr>
                    {% for stock in candidate.top_stocks %}
                      <tr><td>{{ stock.name }} {% if stock.code %}{{ stock.code }}{% endif %}</td><td>{{ "%+.2f"|format(stock.pct_change) }}%</td><td>{{ stock.tags|join("、") }}</td></tr>
                    {% endfor %}
                  </table>
                {% endif %}
```

- [ ] **Step 5: Run tests to verify they pass**

Run:

```bash
cd apps/api && .venv/bin/python -m pytest tests/test_structured_review.py::test_structured_review_uses_front_row_stocks_and_review_sources_in_sector_analysis -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add apps/api/app/services/structured_review_builder.py apps/api/app/renderers/templates/mobile_report.html.j2 apps/api/tests/test_structured_review.py
git commit -m "feat: render strong theme front-row evidence"
```

---

### Task 6: Verification and Real Smoke

**Files:**
- No planned code changes unless tests expose a v0.4 regression.

- [ ] **Step 1: Run focused backend tests**

Run:

```bash
cd apps/api && .venv/bin/python -m pytest tests/test_review_sources.py tests/test_report_api.py tests/test_structured_review.py -v
```

Expected: PASS.

- [ ] **Step 2: Run backend lint**

Run:

```bash
cd apps/api && .venv/bin/python -m ruff check app tests
```

Expected: PASS.

- [ ] **Step 3: Run full backend tests**

Run:

```bash
cd apps/api && .venv/bin/python -m pytest -q
```

Expected: PASS.

- [ ] **Step 4: Generate a real report smoke**

Run the project’s existing report generation command or API smoke command used in previous validation. If no single command exists, start the API and generate `2026-05-26` close report through the local endpoint.

Expected HTML assertions:

```bash
rg -n "复盘源：同花顺复盘|东方财富涨停复盘|前排个股|生益电子|PCB|贵金属|实际最强|去弱留强" reports -g 'report.html'
```

Expected: latest report includes review source attribution and front-row stock table.

- [ ] **Step 5: Browser verify current report**

Open the latest `report.html` in the in-app browser and visually check:

- The first conclusion identifies strong themes, not random stocks.
- Sector cards show front-row stocks and source attribution.
- No `浦发银行` / `平安银行` unless genuinely selected by TickFlow + review source.
- Unavailable source status is shown as failed/disabled, not replaced with fake text.

- [ ] **Step 6: Commit final fixes if needed**

```bash
git add apps/api/app apps/api/tests docs/superpowers/plans/2026-05-27-strong-review-sources-v04-implementation.md
git commit -m "test: verify strong review source pipeline"
```

---

## Self-Review

- Spec coverage: 同花顺 and 东方财富 are the only review sources; TickFlow remains market strength; HTML gets source attribution and front-row stocks.
- Placeholder scan: No implementation step contains TBD/TODO/later placeholders; real smoke command notes use existing project command if available because command name depends on local runner.
- Type consistency: `ReviewSourceResult`, `ReviewThemeEvidence`, `ReviewStockEvidence`, `review_sources`, and `review_notes` are introduced before use.
