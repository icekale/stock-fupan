# Dragon Tiger Daily Report Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integrate Eastmoney dragon tiger board data from `a-stock-data` into daily reports as a compact market sentiment and capital-strength confirmation layer.

**Architecture:** Add typed dragon tiger DTOs to the report schema, implement an Eastmoney datacenter provider in the existing `a_stock_data` provider module, register it as a runtime review source, and wire its summary into report generation. The structured review, next-day prediction, HTML renderer, and quality gate consume only the compact summary, avoiding long seat tables in the report body.

**Tech Stack:** Python 3.12, Pydantic, httpx, FastAPI service layer, pytest, Jinja2 HTML templates, Next.js TypeScript runtime data-source panel tests.

---

## Source Spec

Implement the approved design:

- `docs/superpowers/specs/2026-06-03-dragon-tiger-daily-report-design.md`

## File Structure

- Modify `apps/api/app/schemas/report.py`: add `DragonTigerSummary`, `DragonTigerStock`, `DragonTigerSeat`, and `ReportDTO.dragon_tiger`.
- Modify `apps/api/app/providers/a_stock_data.py`: add `AStockDragonTigerProvider` and Eastmoney datacenter helper methods.
- Modify `apps/api/tests/test_a_stock_data_provider.py`: add provider tests for all-market rows, seat rows, failure degradation, and double-quoted stock filters.
- Modify `apps/api/app/providers/runtime_config.py`: register `a_stock_dragon_tiger` in review source keys and provider options.
- Modify `apps/api/app/providers/factory.py`: instantiate `AStockDragonTigerProvider` when runtime config enables it.
- Modify `apps/api/tests/test_runtime_provider_config.py`: assert runtime config accepts and exposes the new source.
- Modify `apps/web/lib/dataSourceStatusPanel.test.ts`: assert the frontend source panel still uses generic provider-option rendering, so `a_stock_dragon_tiger` needs no hard-coded TypeScript branch.
- Modify `apps/api/app/services/report_generator.py`: capture dragon tiger summary from review source results and persist it on `ReportDTO`, snapshot, and provider status.
- Modify `apps/api/app/services/structured_review_builder.py`: add dragon tiger emotion row, capital summary text, sector capital evidence, and sustainability reasons.
- Modify `apps/api/app/services/next_day_prediction.py`: add dragon tiger basis and scoring impact through `report.dragon_tiger`.
- Modify `apps/api/app/renderers/templates/mobile_report.html.j2`: add compact “龙虎榜情绪确认” section after market sentiment.
- Modify `apps/api/app/rules/quality_gate.py`: add dragon tiger-specific warning behavior when enabled source fails.
- Modify `apps/api/tests/test_report_api.py`, `apps/api/tests/test_structured_review.py`, `apps/api/tests/test_next_day_prediction.py`, `apps/api/tests/test_quality_gate.py`: add contract tests for report wiring, structured review, next-day basis, renderer, and warnings.

---

### Task 1: Add Dragon Tiger Report Schema

**Files:**
- Modify: `apps/api/app/schemas/report.py`
- Test: `apps/api/tests/test_scoring.py`

- [ ] **Step 1: Write the failing schema serialization test**

Append to `apps/api/tests/test_scoring.py`:

```python
def test_report_dto_serializes_dragon_tiger_summary() -> None:
    report = ReportDTO(
        trade_date="2026-06-03",
        kind=ReportKind.CLOSE,
        title="2026-06-03-全日盘后复盘",
        indices=[IndexSnapshot(name="上证指数", code="000001", close=3100.5, pct_change=1.2)],
        breadth=MarketBreadth(up_count=3000, down_count=1800, limit_up_count=60, limit_down_count=3),
        turnover_cny=12000,
        market_state_tags=["结构性修复"],
        sectors=[],
        narrative=ReportNarrative(
            conclusion="短线情绪回暖。",
            overview="指数修复。",
            sector_commentary=[],
            watchlist=[],
            tomorrow="观察承接。",
            risks=[],
        ),
        news=[],
        dragon_tiger=DragonTigerSummary(
            trade_date="2026-06-03",
            source="a-stock-data 东财龙虎榜",
            source_url="https://data.eastmoney.com/stock/lhb.html",
            status="success",
            total_records=91,
            positive_net_count=55,
            negative_net_count=36,
            net_buy_total_wan=268081.1,
            institution_net_buy_wan=19867.4,
            connect_net_buy_wan=82845.9,
            mainline_match_count=2,
            mainline_match_names=["通富微电", "亨通光电"],
            sentiment="strong",
            strength="high",
            conclusion="龙虎榜净买集中在核心方向。",
            risk_notes=["若次日前排高开低走，说明分歧扩大。"],
            top_net_buy=[
                DragonTigerStock(
                    code="002156",
                    name="通富微电",
                    reason="日涨幅偏离值达到7%的前5只证券",
                    close=70.22,
                    change_pct=9.9937,
                    turnover_pct=11.6315,
                    net_buy_wan=162241.5,
                    buy_wan=250982.5,
                    sell_wan=88740.9,
                    seats_buy=[
                        DragonTigerSeat(
                            name="深股通专用",
                            buy_wan=123598.9,
                            sell_wan=40753.0,
                            net_wan=82845.9,
                            role="northbound",
                        )
                    ],
                    seats_sell=[],
                    tags=["净买额Top"],
                )
            ],
            top_net_sell=[],
            highlighted_stocks=[],
        ),
    )

    dumped = report.model_dump(mode="json")

    assert dumped["dragon_tiger"]["status"] == "success"
    assert dumped["dragon_tiger"]["top_net_buy"][0]["name"] == "通富微电"
    assert dumped["dragon_tiger"]["top_net_buy"][0]["seats_buy"][0]["role"] == "northbound"
```

Update the imports in `apps/api/tests/test_scoring.py`:

```python
from app.schemas.report import (
    CapitalEvidence,
    DragonTigerSeat,
    DragonTigerStock,
    DragonTigerSummary,
    IndexSnapshot,
    MarketBreadth,
    ReportDTO,
    ReportKind,
    ReportNarrative,
    SectorCandidate,
    StockCandidate,
)
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
cd apps/api
uv run pytest tests/test_scoring.py::test_report_dto_serializes_dragon_tiger_summary -q
```

Expected: FAIL because the dragon tiger schema classes do not exist.

- [ ] **Step 3: Add schema models**

In `apps/api/app/schemas/report.py`, add these classes after `CapitalEvidence`:

```python
class DragonTigerSeat(BaseModel):
    name: str
    buy_wan: float = 0
    sell_wan: float = 0
    net_wan: float = 0
    role: str = "brokerage"


class DragonTigerStock(BaseModel):
    code: str
    name: str
    reason: str = ""
    close: float | None = None
    change_pct: float | None = None
    turnover_pct: float | None = None
    net_buy_wan: float = 0
    buy_wan: float = 0
    sell_wan: float = 0
    seats_buy: list[DragonTigerSeat] = Field(default_factory=list)
    seats_sell: list[DragonTigerSeat] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class DragonTigerSummary(BaseModel):
    trade_date: str
    source: str = "a-stock-data 东财龙虎榜"
    source_url: str = "https://data.eastmoney.com/stock/lhb.html"
    status: str = "success"
    reason: str | None = None
    total_records: int = 0
    positive_net_count: int = 0
    negative_net_count: int = 0
    net_buy_total_wan: float = 0
    top_net_buy: list[DragonTigerStock] = Field(default_factory=list)
    top_net_sell: list[DragonTigerStock] = Field(default_factory=list)
    highlighted_stocks: list[DragonTigerStock] = Field(default_factory=list)
    institution_net_buy_wan: float = 0
    connect_net_buy_wan: float = 0
    mainline_match_count: int = 0
    mainline_match_names: list[str] = Field(default_factory=list)
    sentiment: str = "unknown"
    strength: str = "unknown"
    conclusion: str = ""
    risk_notes: list[str] = Field(default_factory=list)
```

Then add this field to `ReportDTO` before `previous_strong_themes`:

```python
    dragon_tiger: DragonTigerSummary | None = None
```

- [ ] **Step 4: Run schema test**

Run:

```bash
cd apps/api
uv run pytest tests/test_scoring.py::test_report_dto_serializes_dragon_tiger_summary -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add apps/api/app/schemas/report.py apps/api/tests/test_scoring.py
git commit -m "feat: add dragon tiger report schema"
```

---

### Task 2: Implement Eastmoney Dragon Tiger Provider

**Files:**
- Modify: `apps/api/app/providers/a_stock_data.py`
- Test: `apps/api/tests/test_a_stock_data_provider.py`

- [ ] **Step 1: Write provider tests**

Append to `apps/api/tests/test_a_stock_data_provider.py`:

```python
def test_a_stock_dragon_tiger_maps_all_market_and_seat_payloads() -> None:
    class MultiResponseClient:
        def __init__(self) -> None:
            self.requests: list[dict[str, object]] = []

        def get(self, url: str, **kwargs: object) -> FakeResponse:
            self.requests.append({"url": url, **kwargs})
            params = kwargs["params"]
            report_name = params["reportName"]
            if report_name == "RPT_DAILYBILLBOARD_DETAILSNEW":
                return FakeResponse(
                    {
                        "success": True,
                        "result": {
                            "count": 2,
                            "data": [
                                {
                                    "TRADE_DATE": "2026-06-03 00:00:00",
                                    "SECURITY_CODE": "002156",
                                    "SECURITY_NAME_ABBR": "通富微电",
                                    "EXPLANATION": "日涨幅偏离值达到7%的前5只证券",
                                    "CLOSE_PRICE": 70.22,
                                    "CHANGE_RATE": 9.9937,
                                    "TURNOVERRATE": 11.6315,
                                    "BILLBOARD_NET_AMT": 1622415424.28,
                                    "BILLBOARD_BUY_AMT": 2509824656.64,
                                    "BILLBOARD_SELL_AMT": 887409232.36,
                                },
                                {
                                    "TRADE_DATE": "2026-06-03 00:00:00",
                                    "SECURITY_CODE": "600487",
                                    "SECURITY_NAME_ABBR": "亨通光电",
                                    "EXPLANATION": "非ST连续三日涨幅偏离值累计达到20%",
                                    "CLOSE_PRICE": 91.43,
                                    "CHANGE_RATE": 9.9976,
                                    "TURNOVERRATE": 2.8593,
                                    "BILLBOARD_NET_AMT": 992629307.58,
                                    "BILLBOARD_BUY_AMT": 3032952427.42,
                                    "BILLBOARD_SELL_AMT": 2040323119.84,
                                },
                            ],
                        },
                    }
                )
            return FakeResponse(
                {
                    "success": True,
                    "result": {
                        "count": 2,
                        "data": [
                            {
                                "SECURITY_CODE": "002156",
                                "TRADE_DATE": "2026-06-03 00:00:00",
                                "OPERATEDEPT_NAME": "深股通专用",
                                "BUY": 1235988605.21,
                                "SELL": 407529601.17,
                                "NET": 828459004.04,
                            },
                            {
                                "SECURITY_CODE": "002156",
                                "TRADE_DATE": "2026-06-03 00:00:00",
                                "OPERATEDEPT_NAME": "机构专用",
                                "BUY": 205402058.94,
                                "SELL": 106159009.83,
                                "NET": 99243049.11,
                            },
                        ],
                    },
                }
            )

        def close(self) -> None:
            pass

    client = MultiResponseClient()
    provider = AStockDragonTigerProvider(http_client=client, sleep_seconds=0, max_detail_stocks=1)

    result = provider("2026-06-03")

    assert result.source == "a-stock-data 东财龙虎榜"
    assert result.status == "success"
    assert result.dragon_tiger is not None
    assert result.dragon_tiger.total_records == 2
    assert result.dragon_tiger.top_net_buy[0].name == "通富微电"
    assert result.dragon_tiger.top_net_buy[0].net_buy_wan == 162241.5
    assert result.dragon_tiger.top_net_buy[0].seats_buy[0].role == "northbound"
    assert result.dragon_tiger.top_net_buy[0].seats_buy[1].role == "institution"
    assert result.dragon_tiger.connect_net_buy_wan == 82845.9
    assert result.dragon_tiger.institution_net_buy_wan == 9924.3
    assert result.market_notes[0].startswith("龙虎榜情绪")
    detail_filters = [request["params"]["filter"] for request in client.requests[1:]]
    assert all('SECURITY_CODE="002156"' in value for value in detail_filters)


def test_a_stock_dragon_tiger_degrades_when_detail_request_fails() -> None:
    class DetailFailClient:
        def get(self, url: str, **kwargs: object) -> FakeResponse:
            if kwargs["params"]["reportName"] == "RPT_DAILYBILLBOARD_DETAILSNEW":
                return FakeResponse(
                    {
                        "success": True,
                        "result": {
                            "count": 1,
                            "data": [
                                {
                                    "TRADE_DATE": "2026-06-03 00:00:00",
                                    "SECURITY_CODE": "002156",
                                    "SECURITY_NAME_ABBR": "通富微电",
                                    "BILLBOARD_NET_AMT": 1622415424.28,
                                    "BILLBOARD_BUY_AMT": 2509824656.64,
                                    "BILLBOARD_SELL_AMT": 887409232.36,
                                }
                            ],
                        },
                    }
                )
            raise RuntimeError("detail failed")

        def close(self) -> None:
            pass

    provider = AStockDragonTigerProvider(
        http_client=DetailFailClient(),
        sleep_seconds=0,
        max_detail_stocks=1,
    )

    result = provider("2026-06-03")

    assert result.status == "success"
    assert result.reason == "席位明细部分失败"
    assert result.dragon_tiger is not None
    assert result.dragon_tiger.total_records == 1
    assert result.dragon_tiger.top_net_buy[0].seats_buy == []


def test_a_stock_dragon_tiger_returns_failed_when_all_market_empty() -> None:
    client = FakeClient(FakeResponse({"success": True, "result": {"count": 0, "data": []}}))
    provider = AStockDragonTigerProvider(http_client=client, sleep_seconds=0)

    result = provider("2026-06-03")

    assert result.status == "failed"
    assert result.reason == "东财龙虎榜无结果"
    assert result.dragon_tiger is not None
    assert result.dragon_tiger.status == "failed"
```

Update the import at the top of `apps/api/tests/test_a_stock_data_provider.py`:

```python
from app.providers.a_stock_data import (
    AStockDragonTigerProvider,
    AStockIndustryRankProvider,
    AStockThsHotProvider,
    EastmoneyGlobalNewsProvider,
)
```

- [ ] **Step 2: Run provider tests to verify they fail**

Run:

```bash
cd apps/api
uv run pytest tests/test_a_stock_data_provider.py::test_a_stock_dragon_tiger_maps_all_market_and_seat_payloads tests/test_a_stock_data_provider.py::test_a_stock_dragon_tiger_degrades_when_detail_request_fails tests/test_a_stock_data_provider.py::test_a_stock_dragon_tiger_returns_failed_when_all_market_empty -q
```

Expected: FAIL because `AStockDragonTigerProvider` and `ReviewSourceResult.dragon_tiger` do not exist.

- [ ] **Step 3: Extend review source result**

In `apps/api/app/providers/review_sources.py`, import the schema type:

```python
from app.schemas.report import DragonTigerSummary
```

Add this field to `ReviewSourceResult`:

```python
    dragon_tiger: DragonTigerSummary | None = None
```

- [ ] **Step 4: Implement provider**

In `apps/api/app/providers/a_stock_data.py`, add imports:

```python
import time
from app.schemas.report import DragonTigerSeat, DragonTigerStock, DragonTigerSummary, NewsItem
```

Add class `AStockDragonTigerProvider` after `AStockIndustryRankProvider`:

```python
class AStockDragonTigerProvider:
    source_name = "a-stock-data 东财龙虎榜"

    def __init__(
        self,
        timeout_seconds: float = 12,
        http_client: object | None = None,
        page_size: int = 200,
        max_detail_stocks: int = 5,
        sleep_seconds: float = 1.0,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self._owns_client = http_client is None
        self.http_client = http_client or httpx.Client()
        self.page_size = page_size
        self.max_detail_stocks = max_detail_stocks
        self.sleep_seconds = sleep_seconds
        self.source_url = "https://data.eastmoney.com/stock/lhb.html"
        self.api_url = "https://datacenter-web.eastmoney.com/api/data/v1/get"

    def close(self) -> None:
        if self._owns_client:
            self.http_client.close()

    def __call__(self, trade_date: str) -> ReviewSourceResult:
        try:
            rows = self._datacenter(
                "RPT_DAILYBILLBOARD_DETAILSNEW",
                filter_str=f"(TRADE_DATE>='{trade_date}')(TRADE_DATE<='{trade_date}')",
                page_size=self.page_size,
                sort_columns="BILLBOARD_NET_AMT",
                sort_types="-1",
            )
        except Exception as exc:
            summary = DragonTigerSummary(
                trade_date=trade_date,
                status="failed",
                reason=str(exc) or exc.__class__.__name__,
                conclusion="龙虎榜数据未取得。",
            )
            return ReviewSourceResult(
                source=self.source_name,
                source_url=self.source_url,
                status="failed",
                reason=summary.reason,
                trade_date=trade_date,
                dragon_tiger=summary,
            )
        if not rows:
            summary = DragonTigerSummary(
                trade_date=trade_date,
                status="failed",
                reason="东财龙虎榜无结果",
                conclusion="龙虎榜数据未取得。",
            )
            return ReviewSourceResult(
                source=self.source_name,
                source_url=self.source_url,
                status="failed",
                reason="东财龙虎榜无结果",
                trade_date=trade_date,
                dragon_tiger=summary,
            )

        stocks = [_dragon_tiger_stock(row) for row in rows if isinstance(row, dict)]
        stocks = [stock for stock in stocks if stock.code and stock.name]
        top_net_buy = sorted(stocks, key=lambda stock: stock.net_buy_wan, reverse=True)[:5]
        top_net_sell = sorted(stocks, key=lambda stock: stock.net_buy_wan)[:5]
        detail_failed = False
        for stock in top_net_buy[: self.max_detail_stocks]:
            try:
                self._attach_seats(stock, trade_date)
            except Exception:
                detail_failed = True
            if self.sleep_seconds > 0:
                time.sleep(self.sleep_seconds)

        institution_net = _seat_net_by_role(top_net_buy, "institution")
        connect_net = _seat_net_by_role(top_net_buy, "northbound")
        summary = DragonTigerSummary(
            trade_date=trade_date,
            status="success",
            reason="席位明细部分失败" if detail_failed else None,
            total_records=len(stocks),
            positive_net_count=sum(1 for stock in stocks if stock.net_buy_wan > 0),
            negative_net_count=sum(1 for stock in stocks if stock.net_buy_wan < 0),
            net_buy_total_wan=round(sum(stock.net_buy_wan for stock in stocks), 1),
            top_net_buy=top_net_buy,
            top_net_sell=top_net_sell,
            highlighted_stocks=top_net_buy[:3],
            institution_net_buy_wan=institution_net,
            connect_net_buy_wan=connect_net,
            sentiment=_dragon_tiger_sentiment(stocks, institution_net, connect_net),
            strength=_dragon_tiger_strength(stocks),
            conclusion=_dragon_tiger_conclusion(top_net_buy, institution_net, connect_net),
            risk_notes=_dragon_tiger_risk_notes(top_net_sell),
        )
        return ReviewSourceResult(
            source=self.source_name,
            source_url=self.source_url,
            status="success",
            reason=summary.reason,
            trade_date=trade_date,
            market_notes=_dragon_tiger_market_notes(summary),
            hot_stocks=[
                ReviewStockEvidence(
                    name=stock.name,
                    code=stock.code,
                    pct_change=stock.change_pct,
                    note=stock.reason,
                    source=self.source_name,
                )
                for stock in top_net_buy[:5]
            ],
            dragon_tiger=summary,
        )

    def _datacenter(
        self,
        report_name: str,
        filter_str: str,
        page_size: int,
        sort_columns: str,
        sort_types: str,
    ) -> list[dict[str, Any]]:
        response = self.http_client.get(
            self.api_url,
            headers={
                "User-Agent": UA,
                "Referer": self.source_url,
                "Accept": "application/json,text/plain,*/*",
            },
            params={
                "reportName": report_name,
                "columns": "ALL",
                "filter": filter_str,
                "pageNumber": "1",
                "pageSize": str(page_size),
                "sortColumns": sort_columns,
                "sortTypes": sort_types,
                "source": "WEB",
                "client": "WEB",
            },
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or payload.get("success") is False:
            message = payload.get("message", "东财龙虎榜响应异常") if isinstance(payload, dict) else "东财龙虎榜响应异常"
            raise ProviderFallbackError(str(message))
        rows = payload.get("result", {}).get("data", []) if isinstance(payload.get("result"), dict) else []
        return rows if isinstance(rows, list) else []

    def _attach_seats(self, stock: DragonTigerStock, trade_date: str) -> None:
        filter_str = f"(TRADE_DATE='{trade_date}')(SECURITY_CODE=\"{stock.code}\")"
        buy_rows = self._datacenter(
            "RPT_BILLBOARD_DAILYDETAILSBUY",
            filter_str=filter_str,
            page_size=10,
            sort_columns="BUY",
            sort_types="-1",
        )
        sell_rows = self._datacenter(
            "RPT_BILLBOARD_DAILYDETAILSSELL",
            filter_str=filter_str,
            page_size=10,
            sort_columns="SELL",
            sort_types="-1",
        )
        stock.seats_buy = [_dragon_tiger_seat(row) for row in buy_rows[:5]]
        stock.seats_sell = [_dragon_tiger_seat(row) for row in sell_rows[:5]]
```

Add helper functions near the bottom of `apps/api/app/providers/a_stock_data.py`:

```python
def _dragon_tiger_stock(row: dict[str, Any]) -> DragonTigerStock:
    return DragonTigerStock(
        code=str(row.get("SECURITY_CODE") or ""),
        name=str(row.get("SECURITY_NAME_ABBR") or ""),
        reason=str(row.get("EXPLANATION") or row.get("EXPLAIN") or ""),
        close=_to_float_value(row.get("CLOSE_PRICE")),
        change_pct=_to_float_value(row.get("CHANGE_RATE")),
        turnover_pct=_to_float_value(row.get("TURNOVERRATE")),
        net_buy_wan=round((_to_float_value(row.get("BILLBOARD_NET_AMT")) or 0) / 10000, 1),
        buy_wan=round((_to_float_value(row.get("BILLBOARD_BUY_AMT")) or 0) / 10000, 1),
        sell_wan=round((_to_float_value(row.get("BILLBOARD_SELL_AMT")) or 0) / 10000, 1),
        tags=["龙虎榜"],
    )


def _dragon_tiger_seat(row: dict[str, Any]) -> DragonTigerSeat:
    name = str(row.get("OPERATEDEPT_NAME") or "")
    return DragonTigerSeat(
        name=name,
        buy_wan=round((_to_float_value(row.get("BUY")) or 0) / 10000, 1),
        sell_wan=round((_to_float_value(row.get("SELL")) or 0) / 10000, 1),
        net_wan=round((_to_float_value(row.get("NET")) or 0) / 10000, 1),
        role=_dragon_tiger_seat_role(name),
    )


def _dragon_tiger_seat_role(name: str) -> str:
    if "机构专用" in name:
        return "institution"
    if "沪股通专用" in name or "深股通专用" in name:
        return "northbound"
    return "brokerage"


def _seat_net_by_role(stocks: list[DragonTigerStock], role: str) -> float:
    value = sum(
        seat.net_wan
        for stock in stocks
        for seat in [*stock.seats_buy, *stock.seats_sell]
        if seat.role == role
    )
    return round(value, 1)


def _dragon_tiger_sentiment(
    stocks: list[DragonTigerStock],
    institution_net: float,
    connect_net: float,
) -> str:
    if not stocks:
        return "unknown"
    positive_ratio = sum(1 for stock in stocks if stock.net_buy_wan > 0) / len(stocks)
    top_net = max((stock.net_buy_wan for stock in stocks), default=0)
    if len(stocks) >= 50 and positive_ratio >= 0.55 and top_net >= 10000 and (institution_net > 0 or connect_net > 0):
        return "strong"
    if len(stocks) >= 20 and positive_ratio >= 0.45:
        return "medium"
    return "weak"


def _dragon_tiger_strength(stocks: list[DragonTigerStock]) -> str:
    top_five_total = sum(stock.net_buy_wan for stock in sorted(stocks, key=lambda item: item.net_buy_wan, reverse=True)[:5])
    big_net_count = sum(1 for stock in stocks if stock.net_buy_wan >= 10000)
    if top_five_total >= 50000 and big_net_count >= 2:
        return "high"
    if top_five_total >= 15000 or big_net_count:
        return "normal"
    return "low"


def _dragon_tiger_conclusion(
    top_net_buy: list[DragonTigerStock],
    institution_net: float,
    connect_net: float,
) -> str:
    names = "、".join(stock.name for stock in top_net_buy[:3] if stock.name)
    seat_parts = []
    if institution_net > 0:
        seat_parts.append("机构净买")
    if connect_net > 0:
        seat_parts.append("股通席位净买")
    seat_text = f"，{'、'.join(seat_parts)}参与" if seat_parts else ""
    return f"龙虎榜净买集中在{names or '核心个股'}{seat_text}。"


def _dragon_tiger_risk_notes(top_net_sell: list[DragonTigerStock]) -> list[str]:
    if not top_net_sell:
        return []
    names = "、".join(stock.name for stock in top_net_sell[:3] if stock.net_buy_wan < 0)
    return [f"净卖出集中在{names}，次日需观察高位分歧是否扩大。"] if names else []


def _dragon_tiger_market_notes(summary: DragonTigerSummary) -> list[str]:
    names = "、".join(stock.name for stock in summary.top_net_buy[:3])
    return [
        f"龙虎榜情绪{summary.sentiment}，攻击强度{summary.strength}，净买额集中在{names}。",
        summary.conclusion,
        *summary.risk_notes[:1],
    ]


def _to_float_value(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
```

- [ ] **Step 5: Run provider tests**

Run:

```bash
cd apps/api
uv run pytest tests/test_a_stock_data_provider.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

Run:

```bash
git add apps/api/app/providers/a_stock_data.py apps/api/app/providers/review_sources.py apps/api/tests/test_a_stock_data_provider.py
git commit -m "feat: add eastmoney dragon tiger provider"
```

---

### Task 3: Register Runtime Data Source Option

**Files:**
- Modify: `apps/api/app/providers/runtime_config.py`
- Modify: `apps/api/app/providers/factory.py`
- Modify: `apps/api/tests/test_runtime_provider_config.py`
- Modify: `apps/web/lib/dataSourceStatusPanel.test.ts`

- [ ] **Step 1: Write backend registration test**

Append to `apps/api/tests/test_runtime_provider_config.py`:

```python
def test_runtime_config_accepts_dragon_tiger_review_source() -> None:
    engine = _engine()
    settings = Settings()

    saved = save_runtime_provider_config(
        engine,
        RuntimeProviderConfigInput(
            market_provider="tickflow",
            news_provider="anspire",
            review_sources=["a_stock_dragon_tiger"],
            fallback_enabled=False,
        ),
    )
    payload = build_data_source_options_payload(saved, settings)
    review_category = next(category for category in payload["categories"] if category["key"] == "review_sources")
    dragon_option = next(option for option in review_category["options"] if option["key"] == "a_stock_dragon_tiger")

    assert saved.review_sources == ["a_stock_dragon_tiger"]
    assert dragon_option["label"] == "a-stock 东财龙虎榜"
    assert dragon_option["role"] == "增强源 · 龙虎榜情绪资金"
    assert dragon_option["enabled"] is True
```

Update imports:

```python
from app.providers.runtime_config import (
    RuntimeProviderConfigInput,
    build_data_source_options_payload,
    get_runtime_provider_config,
    save_runtime_provider_config,
)
```

- [ ] **Step 2: Run backend test to verify it fails**

Run:

```bash
cd apps/api
uv run pytest tests/test_runtime_provider_config.py::test_runtime_config_accepts_dragon_tiger_review_source -q
```

Expected: FAIL with `Unsupported REVIEW_SOURCE: a_stock_dragon_tiger`.

- [ ] **Step 3: Register runtime key and option**

In `apps/api/app/providers/runtime_config.py`, extend `ReviewSourceKey`:

```python
    "a_stock_dragon_tiger",
```

Extend `REVIEW_SOURCE_KEYS`:

```python
    "a_stock_dragon_tiger",
```

Add provider option to `PROVIDER_OPTIONS` after `a_stock_industry_rank`:

```python
    ProviderOption("a_stock_dragon_tiger", "review_sources", "a-stock 东财龙虎榜", "增强源 · 龙虎榜情绪资金"),
```

- [ ] **Step 4: Register provider factory**

In `apps/api/app/providers/factory.py`, import `AStockDragonTigerProvider`:

```python
from app.providers.a_stock_data import (
    AStockDragonTigerProvider,
    AStockIndustryRankProvider,
    AStockThsHotProvider,
    EastmoneyGlobalNewsProvider,
)
```

In `_create_review_source_provider()`, add:

```python
    if "a_stock_dragon_tiger" in review_sources:
        providers.append(AStockDragonTigerProvider(timeout_seconds=settings.provider_timeout_seconds))
```

- [ ] **Step 5: Add frontend generic-rendering coverage**

Append these assertions to `apps/web/lib/dataSourceStatusPanel.test.ts` inside `data source panel supports experimental provider status`:

```typescript
assert.match(typesSource, /DataSourceOption/);
assert.doesNotMatch(panelSource, /a_stock_dragon_tiger/);
assert.match(panelSource, /category\.options\.map/);
assert.match(panelSource, /option\.key/);
assert.match(panelSource, /option\.label/);
assert.match(panelSource, /option\.role/);
```

- [ ] **Step 6: Run affected tests**

Run:

```bash
cd apps/api
uv run pytest tests/test_runtime_provider_config.py -q
cd ../web
pnpm test lib/dataSourceStatusPanel.test.ts
```

Expected: PASS.

- [ ] **Step 7: Commit**

Run:

```bash
git add apps/api/app/providers/runtime_config.py apps/api/app/providers/factory.py apps/api/tests/test_runtime_provider_config.py apps/web/lib/dataSourceStatusPanel.test.ts
git commit -m "feat: register dragon tiger data source"
```

---

### Task 4: Wire Dragon Tiger Summary Into Report Generation

**Files:**
- Modify: `apps/api/app/services/report_generator.py`
- Modify: `apps/api/tests/test_report_api.py`

- [ ] **Step 1: Write report generation test**

Append to `apps/api/tests/test_report_api.py`:

```python
def test_report_generator_persists_dragon_tiger_summary(tmp_path: Path) -> None:
    dragon_summary = DragonTigerSummary(
        trade_date="2026-06-03",
        status="success",
        total_records=91,
        positive_net_count=55,
        negative_net_count=36,
        net_buy_total_wan=268081.1,
        sentiment="strong",
        strength="high",
        conclusion="龙虎榜净买集中在通富微电、亨通光电。",
        top_net_buy=[
            DragonTigerStock(
                code="002156",
                name="通富微电",
                reason="日涨幅偏离值达到7%的前5只证券",
                net_buy_wan=162241.5,
                buy_wan=250982.5,
                sell_wan=88740.9,
                tags=["龙虎榜"],
            )
        ],
        top_net_sell=[],
        highlighted_stocks=[],
    )

    class FakeDragonTigerSource:
        def collect(self, trade_date: str):
            return [
                ReviewSourceResult(
                    source="a-stock-data 东财龙虎榜",
                    source_url="https://data.eastmoney.com/stock/lhb.html",
                    status="success",
                    trade_date=trade_date,
                    market_notes=["龙虎榜情绪strong，攻击强度high。"],
                    dragon_tiger=dragon_summary,
                )
            ]

    generator = ReportGenerator(
        reports_root=tmp_path,
        market_provider=FakeMarketDataProvider(),
        news_provider=FakeNewsProvider(),
        llm_provider=FakeLLMProvider(),
        review_source_provider=FakeDragonTigerSource(),
    )

    result = generator.generate_close_report("2026-06-03")
    snapshot = json.loads(result.assets.snapshot.read_text(encoding="utf-8"))
    report_dto = json.loads(result.assets.report_dto.read_text(encoding="utf-8"))

    assert result.report.dragon_tiger is not None
    assert result.report.dragon_tiger.total_records == 91
    assert snapshot["report"]["dragon_tiger"]["top_net_buy"][0]["name"] == "通富微电"
    assert report_dto["dragon_tiger"]["sentiment"] == "strong"
    dragon_status = next(
        item for item in result.provider_status["review_sources"] if item["source"] == "a-stock-data 东财龙虎榜"
    )
    assert dragon_status["record_count"] == 91
```

Update imports in `apps/api/tests/test_report_api.py`:

```python
from app.schemas.report import (
    DragonTigerStock,
    DragonTigerSummary,
    IndexSnapshot,
    ReportDTO,
    ReportKind,
    SectorCandidate,
)
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd apps/api
uv run pytest tests/test_report_api.py::test_report_generator_persists_dragon_tiger_summary -q
```

Expected: FAIL because `ReportGenerator` does not assign `report.dragon_tiger`.

- [ ] **Step 3: Assign dragon tiger summary**

In `apps/api/app/services/report_generator.py`, before constructing `ReportDTO`, add:

```python
        dragon_tiger_summary = _dragon_tiger_summary(review_source_results)
```

In `ReportDTO(...)`, add:

```python
            dragon_tiger=dragon_tiger_summary,
```

Add helper near `_review_source_status`:

```python
def _dragon_tiger_summary(results: list[ReviewSourceResult]):
    for result in results:
        summary = getattr(result, "dragon_tiger", None)
        if summary is not None:
            return summary
    return None
```

Update `_review_source_status()`:

```python
def _review_source_status(result: ReviewSourceResult) -> dict[str, object]:
    dragon_tiger = getattr(result, "dragon_tiger", None)
    payload = {
        "source": result.source,
        "source_url": result.source_url,
        "status": result.status,
        "reason": result.reason,
        "theme_count": len(result.themes),
        "hot_stock_count": len(result.hot_stocks),
    }
    if dragon_tiger is not None:
        payload.update(
            {
                "record_count": dragon_tiger.total_records,
                "seat_detail_count": sum(
                    len(stock.seats_buy) + len(stock.seats_sell)
                    for stock in [*dragon_tiger.top_net_buy, *dragon_tiger.top_net_sell]
                ),
                "dragon_tiger_sentiment": dragon_tiger.sentiment,
                "dragon_tiger_strength": dragon_tiger.strength,
            }
        )
    return payload
```

- [ ] **Step 4: Run report generation test**

Run:

```bash
cd apps/api
uv run pytest tests/test_report_api.py::test_report_generator_persists_dragon_tiger_summary -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add apps/api/app/services/report_generator.py apps/api/tests/test_report_api.py
git commit -m "feat: persist dragon tiger summary in reports"
```

---

### Task 5: Use Dragon Tiger Signals In Structured Review

**Files:**
- Modify: `apps/api/app/services/structured_review_builder.py`
- Test: `apps/api/tests/test_structured_review.py`

- [ ] **Step 1: Write structured review test**

Append to `apps/api/tests/test_structured_review.py`:

```python
def test_build_structured_review_uses_dragon_tiger_sentiment_and_sector_evidence() -> None:
    report = _fake_report()
    report.sectors[0].name = "半导体"
    report.sectors[0].top_stocks = [
        StockCandidate(code="002156", name="通富微电", pct_change=9.99, tags=["TickFlow前排"])
    ]
    report.dragon_tiger = DragonTigerSummary(
        trade_date="2026-06-03",
        status="success",
        total_records=91,
        positive_net_count=55,
        negative_net_count=36,
        net_buy_total_wan=268081.1,
        sentiment="strong",
        strength="high",
        conclusion="龙虎榜净买集中在通富微电、亨通光电。",
        mainline_match_count=1,
        mainline_match_names=["通富微电"],
        top_net_buy=[
            DragonTigerStock(code="002156", name="通富微电", net_buy_wan=162241.5, tags=["龙虎榜"])
        ],
        top_net_sell=[],
        highlighted_stocks=[],
    )

    review = build_structured_review(report)

    assert {"label": "龙虎榜", "value": "强 / high"} in review.market_overview.emotion_rows
    assert "龙虎榜净买集中在通富微电、亨通光电" in review.market_overview.capital_flow_summary
    semiconductor = next(item for item in review.sector_deep_dives if item.sector == "半导体")
    assert any("龙虎榜确认" in item and "通富微电" in item for item in semiconductor.capital_evidence)
    assert any("龙虎榜" in item.reason for item in review.sustainability_ranking)
```

Update imports:

```python
from app.schemas.report import DragonTigerStock, DragonTigerSummary, StockCandidate
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd apps/api
uv run pytest tests/test_structured_review.py::test_build_structured_review_uses_dragon_tiger_sentiment_and_sector_evidence -q
```

Expected: FAIL because structured review ignores `report.dragon_tiger`.

- [ ] **Step 3: Add market overview row and summary**

In `_build_market_overview(report)`, build `emotion_rows` before returning:

```python
    emotion_rows = [
        {"label": "上涨 / 下跌", "value": f"{report.breadth.up_count} / {report.breadth.down_count}"},
        {"label": "涨停 / 跌停", "value": f"{report.breadth.limit_up_count} / {report.breadth.limit_down_count}"},
        {"label": "成交额", "value": f"{report.turnover_cny:.2f} 亿"},
    ]
    if report.dragon_tiger is not None:
        emotion_rows.append(
            {
                "label": "龙虎榜",
                "value": _dragon_tiger_emotion_value(report.dragon_tiger),
            }
        )
```

Use `emotion_rows=emotion_rows` in the DTO.

Change `capital_flow_summary` to:

```python
        capital_flow_summary=_capital_flow_summary(report, strongest_capital),
```

Add helpers:

```python
def _dragon_tiger_emotion_value(summary: object) -> str:
    sentiment = getattr(summary, "sentiment", "unknown")
    strength = getattr(summary, "strength", "unknown")
    labels = {"strong": "强", "medium": "中", "weak": "弱", "unknown": "未知"}
    return f"{labels.get(sentiment, sentiment)} / {strength}"


def _capital_flow_summary(report: ReportDTO, strongest_capital: SectorCandidate | None) -> str:
    dragon_tiger = report.dragon_tiger
    if dragon_tiger is not None and dragon_tiger.status == "success":
        return dragon_tiger.conclusion or "龙虎榜资金已取得，需结合板块前排确认。"
    if strongest_capital and strongest_capital.capital_evidence:
        return (
            f"资金不是简单流入流出，当前更集中在{strongest_capital.name}，"
            f"{strongest_capital.capital_evidence.summary}。"
        )
    return "资金不是简单流入流出，而是在强势板块之间做结构切换。"
```

- [ ] **Step 4: Add sector-level dragon tiger capital notes**

Modify `_sector_capital_notes(sector)` to accept report:

```python
def _sector_capital_notes(sector: SectorCandidate, report: ReportDTO | None = None) -> list[str]:
```

At the top of the function, add:

```python
    if report is not None and report.dragon_tiger is not None:
        matches = _dragon_tiger_sector_matches(report.dragon_tiger, sector)
        if matches:
            notes.append(f"龙虎榜确认：{'、'.join(matches[:3])}进入净买/重点观察名单。")
```

Update caller in `_build_sector_deep_dive()` by adding a `report` parameter and using:

```python
    capital_notes = _sector_capital_notes(sector, report)[:3]
```

Change `_build_sector_deep_dives()` to pass report:

```python
        _build_sector_deep_dive(sector, index, report=report, trade_date=report.trade_date, llm_provider=llm_provider)
```

Add helper:

```python
def _dragon_tiger_sector_matches(summary: object, sector: SectorCandidate) -> list[str]:
    names = {stock.name for stock in sector.top_stocks if stock.name}
    matches = [
        stock.name
        for stock in [*getattr(summary, "top_net_buy", []), *getattr(summary, "highlighted_stocks", [])]
        if stock.name in names or sector.name in stock.reason
    ]
    return _distinct_compact(matches, max_items=5)
```

- [ ] **Step 5: Add sustainability reason mention**

Update `_sustainability_reason(sector)` to accept `report`:

```python
def _sustainability_reason(sector: SectorCandidate, report: ReportDTO | None = None) -> str:
```

At the top:

```python
    if report is not None and report.dragon_tiger is not None:
        matches = _dragon_tiger_sector_matches(report.dragon_tiger, sector)
        if matches:
            return f"评分{sector.score:.1f}，龙虎榜确认{'、'.join(matches[:3])}。"
```

Update the list construction in `build_structured_review()`:

```python
                reason=_sustainability_reason(sector, report),
```

- [ ] **Step 6: Run structured review tests**

Run:

```bash
cd apps/api
uv run pytest tests/test_structured_review.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

Run:

```bash
git add apps/api/app/services/structured_review_builder.py apps/api/tests/test_structured_review.py
git commit -m "feat: use dragon tiger signals in structured review"
```

---

### Task 6: Use Dragon Tiger Signals In Next-Day Prediction

**Files:**
- Modify: `apps/api/app/services/next_day_prediction.py`
- Test: `apps/api/tests/test_next_day_prediction.py`

- [ ] **Step 1: Write next-day prediction test**

Append to `apps/api/tests/test_next_day_prediction.py`:

```python
def test_next_day_prediction_adds_dragon_tiger_basis_for_matching_front_row() -> None:
    report = _prediction_report(
        [
            _sector(
            name="半导体",
            score=80,
            rank=1,
            pct_change=4.2,
            top_stocks=[StockCandidate(code="002156", name="通富微电", pct_change=9.99, tags=["TickFlow前排"])],
            review_sources=["同花顺复盘", "东方财富涨停复盘"],
            review_notes=["半导体强势"],
            )
        ]
    )
    report.dragon_tiger = DragonTigerSummary(
        trade_date="2026-06-03",
        status="success",
        sentiment="strong",
        strength="high",
        conclusion="龙虎榜净买集中在通富微电。",
        top_net_buy=[DragonTigerStock(code="002156", name="通富微电", net_buy_wan=162241.5, tags=["龙虎榜"])],
        top_net_sell=[],
        highlighted_stocks=[],
    )

    prediction = build_next_day_predictions(report)[0]

    assert any("龙虎榜" in item and "通富微电" in item for item in prediction.primary_basis)
    assert any("龙虎榜资金确认" in item for item in prediction.evidence_notes)
    assert prediction.score_breakdown is not None
    assert prediction.score_breakdown.capital_strength >= 8
```

Update imports:

```python
from app.schemas.report import DragonTigerStock, DragonTigerSummary
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd apps/api
uv run pytest tests/test_next_day_prediction.py::test_next_day_prediction_adds_dragon_tiger_basis_for_matching_front_row -q
```

Expected: FAIL because prediction does not include dragon tiger basis.

- [ ] **Step 3: Add dragon tiger basis**

In `_primary_basis(sector)`, accept `report`:

```python
def _primary_basis(report: ReportDTO, sector: SectorCandidate) -> list[str]:
```

Append:

```python
    dragon_basis = _dragon_tiger_basis(report, sector)
    if dragon_basis:
        basis.append(dragon_basis)
```

Update callers from `_primary_basis(sector)` to `_primary_basis(report, sector)`.

Add helper:

```python
def _dragon_tiger_basis(report: ReportDTO, sector: SectorCandidate) -> str | None:
    summary = report.dragon_tiger
    if summary is None or summary.status != "success":
        return None
    names = {stock.name for stock in sector.top_stocks if stock.name}
    matches = [
        stock
        for stock in [*summary.top_net_buy, *summary.highlighted_stocks]
        if stock.name in names or sector.name in stock.reason
    ]
    if not matches:
        return None
    first = matches[0]
    return f"龙虎榜资金：{first.name}净买{first.net_buy_wan:.1f}万，情绪{summary.sentiment}，强度{summary.strength}"
```

- [ ] **Step 4: Add dragon tiger scoring and notes**

In `_score_breakdown()`, add to `capital_strength`:

```python
    capital_strength = _capital_strength_points(sector) + _dragon_tiger_points(report, sector)
```

Add helper:

```python
def _dragon_tiger_points(report: ReportDTO, sector: SectorCandidate) -> int:
    summary = report.dragon_tiger
    if summary is None or summary.status != "success":
        return 0
    names = {stock.name for stock in sector.top_stocks if stock.name}
    has_positive_match = any(
        stock.name in names and stock.net_buy_wan > 0
        for stock in summary.top_net_buy
    )
    has_negative_match = any(
        stock.name in names and stock.net_buy_wan < 0
        for stock in summary.top_net_sell
    )
    if has_negative_match:
        return -6
    if has_positive_match and summary.sentiment == "strong":
        return 6
    if has_positive_match:
        return 3
    return 0
```

In `_evidence_notes(sector)`, accept report and add:

```python
def _evidence_notes(report: ReportDTO, sector: SectorCandidate) -> list[str]:
    notes = [*sector.review_notes, *sector.news_summaries]
    basis = _dragon_tiger_basis(report, sector)
    if basis:
        notes.append(f"龙虎榜资金确认：{basis}")
    return _dedupe(notes)[:4]
```

Update callers to `_evidence_notes(report, sector)`.

- [ ] **Step 5: Run next-day tests**

Run:

```bash
cd apps/api
uv run pytest tests/test_next_day_prediction.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

Run:

```bash
git add apps/api/app/services/next_day_prediction.py apps/api/tests/test_next_day_prediction.py
git commit -m "feat: add dragon tiger next-day prediction basis"
```

---

### Task 7: Render Compact Dragon Tiger Section

**Files:**
- Modify: `apps/api/app/renderers/templates/mobile_report.html.j2`
- Test: `apps/api/tests/test_structured_review.py`

- [ ] **Step 1: Write renderer test**

Append to `apps/api/tests/test_structured_review.py`:

```python
def test_mobile_template_contains_compact_dragon_tiger_section() -> None:
    template = Path("app/renderers/templates/mobile_report.html.j2").read_text(encoding="utf-8")

    assert "龙虎榜情绪确认" in template
    assert "report.dragon_tiger" in template
    assert "top_net_buy[:3]" in template
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd apps/api
uv run pytest tests/test_structured_review.py::test_mobile_template_contains_compact_dragon_tiger_section -q
```

Expected: FAIL because the section is not present.

- [ ] **Step 3: Add compact section after market sentiment**

In `apps/api/app/renderers/templates/mobile_report.html.j2`, after the “情绪阶段判断” key insight block and before `structured.prediction_verifications`, add:

```jinja2
    {% if report.dragon_tiger %}
      <h3 class="section-subtitle">龙虎榜情绪确认</h3>
      <div class="key-insight">
        {% if report.dragon_tiger.status == "success" %}
          <div class="ki-title">情绪 {{ report.dragon_tiger.sentiment }} · 强度 {{ report.dragon_tiger.strength }}</div>
          <p>{{ report.dragon_tiger.conclusion }}</p>
          {% if report.dragon_tiger.top_net_buy %}
            <p style="margin-top:10px;">
              <strong>净买前排：</strong>
              {% for stock in report.dragon_tiger.top_net_buy[:3] %}
                {{ stock.name }} {{ "%.1f"|format(stock.net_buy_wan) }}万{% if not loop.last %}、{% endif %}
              {% endfor %}
            </p>
          {% endif %}
          {% if report.dragon_tiger.mainline_match_names %}
            <p style="margin-top:10px;"><strong>主线匹配：</strong>{{ report.dragon_tiger.mainline_match_names[:3]|join("、") }}</p>
          {% endif %}
          {% if report.dragon_tiger.risk_notes %}
            <ul class="point-list" style="margin-top:10px;">
              {% for item in report.dragon_tiger.risk_notes[:2] %}
                <li>{{ item }}</li>
              {% endfor %}
            </ul>
          {% endif %}
        {% else %}
          <div class="ki-title">龙虎榜数据未取得</div>
          <p>{{ report.dragon_tiger.reason or "东财龙虎榜暂未返回可用数据。" }}</p>
        {% endif %}
      </div>
    {% endif %}
```

- [ ] **Step 4: Run renderer test**

Run:

```bash
cd apps/api
uv run pytest tests/test_structured_review.py::test_mobile_template_contains_compact_dragon_tiger_section -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add apps/api/app/renderers/templates/mobile_report.html.j2 apps/api/tests/test_structured_review.py
git commit -m "feat: render dragon tiger sentiment section"
```

---

### Task 8: Add Dragon Tiger Quality Gate Warnings

**Files:**
- Modify: `apps/api/app/rules/quality_gate.py`
- Test: `apps/api/tests/test_quality_gate.py`

- [ ] **Step 1: Write quality gate test**

Append to `apps/api/tests/test_quality_gate.py`:

```python
def test_quality_gate_warns_when_enabled_dragon_tiger_source_fails() -> None:
    from app.rules.quality_gate import evaluate_quality_gate

    report = make_report()
    validation = ValidationResult(is_valid=True, errors=[])
    provider_status = success_provider_status()
    provider_status["review_sources"].append(
        {
            "source": "a-stock-data 东财龙虎榜",
            "source_url": "https://data.eastmoney.com/stock/lhb.html",
            "status": "failed",
            "reason": "东财龙虎榜无结果",
            "record_count": 0,
            "seat_detail_count": 0,
        }
    )

    result = evaluate_quality_gate(
        report=report,
        validation=validation,
        provider_status=provider_status,
        structured_review_status={"provider": "rule", "status": "success", "fallback_used": False},
    )

    assert any(issue.code == "dragon_tiger_source_failed" for issue in result.warnings)
    assert result.score is not None
    assert result.score <= 95
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd apps/api
uv run pytest tests/test_quality_gate.py::test_quality_gate_warns_when_enabled_dragon_tiger_source_fails -q
```

Expected: FAIL because the warning is not emitted.

- [ ] **Step 3: Add warning logic**

In `evaluate_quality_gate()`, after board rank warning logic, add:

```python
    if _has_failed_dragon_tiger_source(provider_status):
        score -= 5
        warnings.append(
            _issue(
                "dragon_tiger_source_failed",
                "warning",
                "龙虎榜源失败，情绪资金确认降级",
                {"penalty": 5},
            )
        )
```

Add helper:

```python
def _has_failed_dragon_tiger_source(provider_status: dict[str, object]) -> bool:
    for item in _as_list(provider_status.get("review_sources")):
        source = str(_as_dict(item).get("source", ""))
        status = str(_as_dict(item).get("status", ""))
        if "龙虎榜" in source and status != "success":
            return True
    return False
```

- [ ] **Step 4: Run quality gate tests**

Run:

```bash
cd apps/api
uv run pytest tests/test_quality_gate.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add apps/api/app/rules/quality_gate.py apps/api/tests/test_quality_gate.py
git commit -m "feat: warn on dragon tiger source failure"
```

---

### Task 9: End-to-End Verification

**Files:**
- No new files required.
- Verify: API tests, web tests, lint, local report generation.

- [ ] **Step 1: Run focused API tests**

Run:

```bash
cd apps/api
uv run pytest \
  tests/test_a_stock_data_provider.py \
  tests/test_runtime_provider_config.py \
  tests/test_report_api.py::test_report_generator_persists_dragon_tiger_summary \
  tests/test_structured_review.py::test_build_structured_review_uses_dragon_tiger_sentiment_and_sector_evidence \
  tests/test_structured_review.py::test_mobile_template_contains_compact_dragon_tiger_section \
  tests/test_next_day_prediction.py::test_next_day_prediction_adds_dragon_tiger_basis_for_matching_front_row \
  tests/test_quality_gate.py::test_quality_gate_warns_when_enabled_dragon_tiger_source_fails \
  -q
```

Expected: PASS.

- [ ] **Step 2: Run full API test suite**

Run:

```bash
cd apps/api
uv run pytest -q
```

Expected: PASS.

- [ ] **Step 3: Run API lint**

Run:

```bash
cd apps/api
uv run ruff check .
```

Expected: PASS.

- [ ] **Step 4: Run web tests**

Run:

```bash
cd apps/web
pnpm test
```

Expected: PASS.

- [ ] **Step 5: Run live dragon tiger provider probe**

Run:

```bash
cd apps/api
uv run python - <<'PY'
from app.providers.a_stock_data import AStockDragonTigerProvider

provider = AStockDragonTigerProvider(sleep_seconds=1.0, max_detail_stocks=2)
try:
    result = provider("2026-06-03")
    print(result.status)
    print(result.dragon_tiger.total_records if result.dragon_tiger else None)
    print([stock.name for stock in (result.dragon_tiger.top_net_buy[:3] if result.dragon_tiger else [])])
finally:
    provider.close()
PY
```

Expected for the verified `2026-06-03` sample:

```text
success
91
['通富微电', '亨通光电', '国机精工']
```

If Eastmoney live output changes on a later run, record the actual `total_records` and top-three names in the execution notes before proceeding.

- [ ] **Step 6: Enable dragon tiger source through runtime config**

Run:

```bash
cd apps/api
uv run python - <<'PY'
from app.config import Settings
from app.db.session import create_sqlite_engine, init_db
from app.providers.runtime_config import RuntimeProviderConfigInput, save_runtime_provider_config

settings = Settings()
engine = create_sqlite_engine(settings.database_url)
init_db(engine)
save_runtime_provider_config(
    engine,
    RuntimeProviderConfigInput(
        market_provider=settings.market_provider,
        news_provider=settings.news_provider,
        review_sources=[
            "a_stock_ths_hot",
            "a_stock_industry_rank",
            "a_stock_dragon_tiger",
        ],
        fallback_enabled=settings.provider_fallback_enabled,
    ),
)
print("enabled a_stock_dragon_tiger")
PY
```

Expected:

```text
enabled a_stock_dragon_tiger
```

- [ ] **Step 7: Generate an HTML report through existing command**

Run:

```bash
make report DATE=2026-06-03 KIND=close
```

Expected:

- Command exits successfully.
- Generated `report_dto.json` includes a non-null `dragon_tiger`.
- Generated `report.html` contains `龙虎榜情绪确认`.
- The module is compact and does not render a full seat table.

- [ ] **Step 8: Inspect git status**

Run:

```bash
git status --short
```

Expected: only intended implementation files changed, plus generated reports ignored by git.

- [ ] **Step 9: Final commit when verification produced additional edits**

Run:

```bash
git add apps/api apps/web
git commit -m "feat: integrate dragon tiger signals into daily reports"
```

Expected: commit succeeds when `git status --short` shows remaining implementation changes after the task-level commits.

---

## Completion Criteria

- `a_stock_dragon_tiger` appears in backend data-source options.
- Enabling `a_stock_dragon_tiger` creates `AStockDragonTigerProvider`.
- `ReportDTO.dragon_tiger` serializes to `report_dto.json` and `snapshot.json`.
- Structured review includes a dragon tiger emotion row and sector capital evidence when matching front-row stocks appear on the board.
- Next-day predictions include dragon tiger basis and scoring impact for matched front-row stocks.
- HTML report contains a compact “龙虎榜情绪确认” module.
- Quality gate warns when the enabled dragon tiger source fails.
- Focused and full test suites pass.
