import httpx
import pytest

from app.providers.market import ProviderFallbackError
from app.providers.tickflow import (
    FallbackTickFlowProvider,
    FakeTickFlowProvider,
    TickFlowMarketDataProvider,
    TickFlowProvider,
    WatchlistQuote,
)
from app.providers.ths_concepts import ThsConceptBoardProvider
from app.rules.scoring import RawSectorInput


class FakeResponse:
    def __init__(self, payload: object, status_code: int = 200) -> None:
        self.payload = payload
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                "boom",
                request=httpx.Request("POST", "https://api.test"),
                response=httpx.Response(self.status_code),
            )

    def json(self) -> object:
        return self.payload


class FakeClient:
    def __init__(self, response: FakeResponse | None = None, error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.last_request: dict[str, object] = {}
        self.closed = False

    def post(self, url: str, **kwargs: object) -> FakeResponse:
        self.last_request = {"url": url, **kwargs}
        if self.error is not None:
            raise self.error
        assert self.response is not None
        return self.response

    def close(self) -> None:
        self.closed = True


class RouteClient:
    def __init__(self, responses: dict[tuple[str, str], FakeResponse]) -> None:
        self.responses = responses
        self.requests: list[dict[str, object]] = []

    def get(self, url: str, **kwargs: object) -> FakeResponse:
        params = kwargs.get("params")
        key = (url, _route_param_key(params))
        self.requests.append({"method": "GET", "url": url, **kwargs})
        return self.responses[key]

    def post(self, url: str, **kwargs: object) -> FakeResponse:
        params = kwargs.get("json") or {}
        symbols = ",".join(params.get("symbols", [])) if isinstance(params, dict) else ""
        key = (url, symbols)
        self.requests.append({"method": "POST", "url": url, **kwargs})
        return self.responses[key]

    def close(self) -> None:
        pass


class TrackingTickFlowProvider(TickFlowProvider):
    def __init__(
        self,
        quotes: list[WatchlistQuote],
    ) -> None:
        self.quotes = quotes

    def get_universe_quotes(self, universe_id: str) -> list[WatchlistQuote]:
        return self.quotes

    def get_quotes(self, symbols: list[str]) -> list[WatchlistQuote]:
        return [quote for quote in self.quotes if quote.symbol in symbols]

    def close(self) -> None:
        pass


class TrackingThsConceptProvider:
    def __init__(self) -> None:
        self.calls: list[tuple[str, list[str]]] = []

    def build_sector_input(
        self,
        sector_name: str,
        quotes: list[WatchlistQuote],
        trade_date: str | None = None,
    ) -> RawSectorInput | None:
        self.calls.append((sector_name, [quote.name or quote.symbol for quote in quotes]))
        if sector_name != "PCB":
            return None
        return RawSectorInput(
            name="PCB",
            pct_change=4.8,
            limit_up_count=2,
            stock_up_ratio=1.0,
            turnover_change=0.42,
            news_weight=0.76,
        )


class NoConceptProvider:
    def build_sector_input(
        self,
        sector_name: str,
        quotes: list[WatchlistQuote],
        trade_date: str | None = None,
    ) -> RawSectorInput | None:
        return None

    def close(self) -> None:
        pass


class FakeThsAkshare:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    def stock_board_concept_name_ths(self) -> list[dict[str, object]]:
        return [{"name": "PCB概念", "code": "308832"}]

    def stock_board_concept_info_ths(self, **kwargs: object) -> list[dict[str, object]]:
        self.calls.append(("info", kwargs))
        return [
            {"项目": "板块涨幅", "值": "3.47%"},
            {"项目": "涨跌家数", "值": "171/40"},
            {"项目": "资金净流入(亿)", "值": "88.49"},
            {"项目": "成交额(亿)", "值": "3487.93"},
        ]

    def stock_board_concept_index_ths(self, **kwargs: object) -> list[dict[str, object]]:
        self.calls.append(("index", kwargs))
        return [
            {"日期": "2026-05-27", "收盘价": "2845.327"},
            {"日期": "2026-05-28", "收盘价": "2944.041"},
        ]


def _route_param_key(params: object) -> str:
    if not isinstance(params, dict):
        return ""
    return str(params.get("universes") or "")


def test_tickflow_provider_maps_batch_quotes() -> None:
    client = FakeClient(
        FakeResponse(
            {
                "data": [
                    {
                        "symbol": "600000.SH",
                        "name": "浦发银行",
                        "last_price": 10.5,
                        "pct_change": 2.3,
                        "turnover": 123000000,
                        "volume": 45600,
                        "time": "2026-05-26T15:00:00+08:00",
                    }
                ]
            }
        )
    )
    provider = TickFlowProvider(
        api_key="tk-test-local",
        base_url="https://api.tickflow.org",
        http_client=client,
    )

    quotes = provider.get_quotes(["600000.SH"])

    assert quotes[0].symbol == "600000.SH"
    assert quotes[0].name == "浦发银行"
    assert quotes[0].pct_change == 2.3
    assert client.last_request["url"] == "https://api.tickflow.org/v1/quotes"
    assert client.last_request["headers"] == {"x-api-key": "tk-test-local"}


def test_tickflow_provider_maps_nested_ext_quote_fields() -> None:
    client = FakeClient(
        FakeResponse(
            {
                "data": [
                    {
                        "symbol": "600000.SH",
                        "last_price": 9.27,
                        "volume": 1464375,
                        "amount": 135000000,
                        "timestamp": "1779778804000",
                        "ext": {
                            "name": "浦发银行",
                            "change_pct": 0.020925110132158534,
                            "turnover_rate": 0.0185,
                        },
                    }
                ]
            }
        )
    )
    provider = TickFlowProvider(
        api_key="tk-test-local",
        base_url="https://api.tickflow.org",
        http_client=client,
    )

    quotes = provider.get_quotes(["600000.SH"])

    assert quotes[0].name == "浦发银行"
    assert quotes[0].pct_change == pytest.approx(2.0925110132158534)
    assert quotes[0].turnover_cny == 135000000
    assert quotes[0].turnover_rate == pytest.approx(1.85)
    assert quotes[0].quote_time == "1779778804000"


def test_tickflow_market_provider_builds_snapshot_from_real_quotes() -> None:
    client = RouteClient(
        {
            ("https://api.tickflow.org/v1/quotes", "CN_Equity_A"): FakeResponse(
                {
                    "data": [
                        {
                            "symbol": "000001.SH",
                            "last_price": 4145.37,
                            "amount": 500000000000,
                            "ext": {"name": "上证指数", "change_pct": -0.0017},
                        },
                        {
                            "symbol": "399006.SZ",
                            "last_price": 2600.12,
                            "amount": 300000000000,
                            "ext": {"name": "创业板指", "change_pct": 0.012},
                        },
                        {
                            "symbol": "600000.SH",
                            "last_price": 9.27,
                            "amount": 1350000000,
                            "ext": {"name": "浦发银行", "change_pct": 0.0209},
                        },
                        {
                            "symbol": "000001.SZ",
                            "last_price": 10.79,
                            "amount": 900000000,
                            "ext": {"name": "平安银行", "change_pct": 0.0102},
                        },
                        {
                            "symbol": "300750.SZ",
                            "last_price": 402.5,
                            "amount": 14100000000,
                            "ext": {"name": "宁德时代", "change_pct": -0.0009},
                        },
                    ]
                }
            ),
            ("https://api.tickflow.org/v1/universes", ""): FakeResponse({"data": []}),
        }
    )
    provider = TickFlowMarketDataProvider(
        api_key="tk-test-local",
        base_url="https://api.tickflow.org",
        symbols=["600000.SH", "000001.SZ", "300750.SZ"],
        http_client=client,
        concept_provider=NoConceptProvider(),
    )

    snapshot = provider.get_close_snapshot("2026-05-27")

    assert snapshot.indices[0].name == "上证指数"
    assert snapshot.indices[0].pct_change == pytest.approx(-0.17)
    assert snapshot.breadth.up_count == 2
    assert snapshot.breadth.down_count == 1
    assert snapshot.turnover_cny == pytest.approx(163.5)
    assert snapshot.raw_sectors[0].name == "浦发银行"
    assert snapshot.raw_sectors[0].pct_change == pytest.approx(2.09)


def test_tickflow_market_provider_uses_full_market_and_theme_strength() -> None:
    client = RouteClient(
        {
            ("https://api.tickflow.org/v1/quotes", "CN_Equity_A"): FakeResponse(
                {
                    "data": [
                        {
                            "symbol": "000001.SH",
                            "last_price": 4145.37,
                            "amount": 500000000000,
                            "ext": {"name": "上证指数", "change_pct": -0.0017},
                        },
                        {
                            "symbol": "399006.SZ",
                            "last_price": 2600.12,
                            "amount": 300000000000,
                            "ext": {"name": "创业板指", "change_pct": 0.012},
                        },
                        {
                            "symbol": "688183.SH",
                            "last_price": 132.1,
                            "amount": 9708665000,
                            "ext": {"name": "生益电子", "change_pct": 0.2000},
                        },
                        {
                            "symbol": "002463.SZ",
                            "last_price": 52.6,
                            "amount": 1200000000,
                            "ext": {"name": "沪电股份", "change_pct": 0.101},
                        },
                        {
                            "symbol": "688335.SH",
                            "last_price": 31.88,
                            "amount": 270323900,
                            "ext": {"name": "复洁科技", "change_pct": 0.1998},
                        },
                        {
                            "symbol": "600000.SH",
                            "last_price": 9.27,
                            "amount": 1350000000,
                            "ext": {"name": "浦发银行", "change_pct": 0.0209},
                        },
                        {
                            "symbol": "920575.BJ",
                            "last_price": 4.2,
                            "amount": 90455200,
                            "ext": {"name": "*ST康乐", "change_pct": 0.20},
                        },
                    ]
                }
            ),
        }
    )
    provider = TickFlowMarketDataProvider(
        api_key="tk-test-local",
        base_url="https://api.tickflow.org",
        http_client=client,
        concept_provider=NoConceptProvider(),
    )

    snapshot = provider.get_close_snapshot("2026-05-27")

    requested_universes = [
        request.get("params", {}).get("universes")
        for request in client.requests
        if request["method"] == "GET" and request["url"].endswith("/quotes")
    ]
    assert "CN_Equity_A" in requested_universes
    assert snapshot.raw_sectors[0].name == "PCB"
    assert snapshot.raw_sectors[0].pct_change == pytest.approx(15.05)
    assert snapshot.raw_sectors[0].limit_up_count == 2
    assert all(sector.name != "浦发银行" for sector in snapshot.raw_sectors)
    assert snapshot.breadth.limit_up_count == 3


def test_tickflow_market_provider_uses_ths_concept_boards_for_sector_grouping() -> None:
    quotes = [
        WatchlistQuote(symbol="688183.SH", name="生益电子", pct_change=20, turnover_cny=9_700_000_000),
        WatchlistQuote(symbol="002463.SZ", name="沪电股份", pct_change=10.1, turnover_cny=1_200_000_000),
        WatchlistQuote(symbol="688335.SH", name="复洁科技", pct_change=19.98, turnover_cny=270_000_000),
        WatchlistQuote(symbol="300234.SZ", name="开尔新材", pct_change=14.65, turnover_cny=440_000_000),
        WatchlistQuote(symbol="600000.SH", name="浦发银行", pct_change=2.09, turnover_cny=1_350_000_000),
    ]

    provider = TickFlowMarketDataProvider(
        api_key="tk-test-local",
        base_url="https://api.tickflow.org",
        concept_provider=TrackingThsConceptProvider(),
    )

    sectors = provider._strong_sectors_from_market(quotes)

    assert sectors[0].name == "PCB"
    assert sectors[0].pct_change == pytest.approx(4.8)
    assert sectors[0].limit_up_count == 2
    assert ("PCB", ["生益电子", "沪电股份"]) in provider.concept_provider.calls


def test_ths_concept_provider_uses_resolved_concept_name_and_board_stats() -> None:
    akshare = FakeThsAkshare()
    provider = ThsConceptBoardProvider(akshare_module=akshare)

    sector = provider.build_sector_input(
        "PCB",
        [
            WatchlistQuote(symbol="688183.SH", name="生益电子", pct_change=20),
            WatchlistQuote(symbol="002463.SZ", name="沪电股份", pct_change=10.1),
        ],
        trade_date="2026-05-28",
    )

    assert sector is not None
    assert sector.name == "PCB概念"
    assert sector.pct_change == pytest.approx(3.47)
    assert sector.stock_up_ratio == pytest.approx(171 / 211, abs=0.0001)
    assert sector.turnover_change == pytest.approx(88.49 / 3487.93, abs=0.0001)
    assert ("info", {"symbol": "PCB概念"}) in akshare.calls
    assert (
        "index",
        {"symbol": "PCB概念", "start_date": "20260518", "end_date": "20260528"},
    ) in akshare.calls


def test_tickflow_market_provider_groups_strong_stocks_into_themes() -> None:
    quotes = [
        WatchlistQuote(symbol="688183.SH", name="生益电子", pct_change=20, turnover_cny=9_700_000_000),
        WatchlistQuote(symbol="002463.SZ", name="沪电股份", pct_change=10.1, turnover_cny=1_200_000_000),
        WatchlistQuote(symbol="688335.SH", name="复洁科技", pct_change=19.98, turnover_cny=270_000_000),
        WatchlistQuote(symbol="300234.SZ", name="开尔新材", pct_change=14.65, turnover_cny=440_000_000),
        WatchlistQuote(symbol="600000.SH", name="浦发银行", pct_change=2.09, turnover_cny=1_350_000_000),
    ]

    provider = TickFlowMarketDataProvider(api_key="tk-test-local", base_url="https://api.tickflow.org", concept_provider=NoConceptProvider())
    sectors = provider._strong_sectors_from_market(quotes)

    assert sectors[0].name == "PCB"
    assert sectors[0].limit_up_count == 2
    assert any(sector.name == "环保" for sector in sectors)
    assert all(sector.name != "浦发银行" for sector in sectors)


def test_tickflow_market_provider_keeps_specific_chip_concept_themes() -> None:
    quotes = [
        WatchlistQuote(symbol="600584.SH", name="长电科技", pct_change=10.2, turnover_cny=4_700_000_000),
        WatchlistQuote(symbol="002156.SZ", name="通富微电", pct_change=10.0, turnover_cny=3_600_000_000),
        WatchlistQuote(symbol="688525.SH", name="佰维存储", pct_change=20.0, turnover_cny=4_200_000_000),
        WatchlistQuote(symbol="001309.SZ", name="德明利", pct_change=10.0, turnover_cny=2_500_000_000),
    ]

    provider = TickFlowMarketDataProvider(
        api_key="tk-test-local",
        base_url="https://api.tickflow.org",
        concept_provider=NoConceptProvider(),
    )

    sectors = provider._strong_sectors_from_market(quotes)
    sector_names = [sector.name for sector in sectors]

    assert sector_names[:2] == ["存储芯片", "先进封装"]
    assert "半导体" not in sector_names


def test_tickflow_market_provider_does_not_classify_jinpan_as_nonferrous_by_single_character() -> None:
    quotes = [
        WatchlistQuote(symbol="688676.SH", name="金盘科技", pct_change=10.5, turnover_cny=2_700_000_000),
        WatchlistQuote(symbol="600489.SH", name="中金黄金", pct_change=10.0, turnover_cny=3_000_000_000),
        WatchlistQuote(symbol="600547.SH", name="山东黄金", pct_change=9.9, turnover_cny=2_000_000_000),
    ]

    provider = TickFlowMarketDataProvider(api_key="tk-test-local", base_url="https://api.tickflow.org", concept_provider=NoConceptProvider())
    sectors = provider._strong_sectors_from_market(quotes)
    nonferrous = next(sector for sector in sectors if sector.name == "有色金属")

    assert nonferrous.limit_up_count == 2
    assert [quote.name for quote in provider.get_sector_frontline_stocks("有色金属")] == [
        "中金黄金",
        "山东黄金",
    ]


def test_tickflow_market_provider_exposes_frontline_stocks_for_ranked_sectors() -> None:
    quotes = [
        WatchlistQuote(
            symbol="688183.SH",
            name="生益电子",
            pct_change=20,
            turnover_cny=9_700_000_000,
            turnover_rate=18.5,
        ),
        WatchlistQuote(
            symbol="002463.SZ",
            name="沪电股份",
            pct_change=10.1,
            turnover_cny=1_200_000_000,
            turnover_rate=6.2,
        ),
        WatchlistQuote(symbol="688335.SH", name="复洁科技", pct_change=19.98, turnover_cny=270_000_000),
        WatchlistQuote(symbol="300234.SZ", name="开尔新材", pct_change=14.65, turnover_cny=440_000_000),
        WatchlistQuote(symbol="600000.SH", name="浦发银行", pct_change=2.09, turnover_cny=1_350_000_000),
    ]
    provider = TickFlowMarketDataProvider(
        api_key="tk-test-local",
        base_url="https://api.tickflow.org",
        concept_provider=NoConceptProvider(),
    )

    sectors = provider._strong_sectors_from_market(quotes)
    pcb_frontline = provider.get_sector_frontline_stocks("PCB")

    assert sectors[0].name == "PCB"
    assert [quote.name for quote in pcb_frontline] == ["生益电子", "沪电股份"]
    assert pcb_frontline[0].capital_strength == "强"
    assert pcb_frontline[0].turnover_rate == pytest.approx(18.5)
    assert all((quote.pct_change or 0) >= 9.8 for quote in pcb_frontline)


def test_tickflow_market_provider_uses_ths_concept_boards_when_available() -> None:
    quotes = [
        WatchlistQuote(symbol="000001.SH", name="上证指数", last_price=4100, pct_change=0.2, turnover_cny=1),
        WatchlistQuote(symbol="399006.SZ", name="创业板指", last_price=2200, pct_change=0.5, turnover_cny=1),
        WatchlistQuote(symbol="688676.SH", name="金盘科技", pct_change=11.04, turnover_cny=2_700_000_000),
        WatchlistQuote(symbol="600489.SH", name="中金黄金", pct_change=10.0, turnover_cny=3_000_000_000),
        WatchlistQuote(symbol="600547.SH", name="山东黄金", pct_change=9.9, turnover_cny=2_000_000_000),
        WatchlistQuote(symbol="603663.SH", name="三祥新材", pct_change=10.0, turnover_cny=1_200_000_000),
    ]
    provider = TickFlowMarketDataProvider(api_key="tk-test-local", base_url="https://api.tickflow.org", concept_provider=NoConceptProvider())
    provider.quote_provider = TrackingTickFlowProvider(
        quotes=quotes,
    )

    snapshot = provider.get_close_snapshot("2026-05-26")

    nonferrous = next(sector for sector in snapshot.raw_sectors if sector.name == "有色金属")
    nonferrous_frontline = provider.get_sector_frontline_stocks("有色金属")
    assert nonferrous.limit_up_count == 2
    assert [quote.name for quote in nonferrous_frontline] == ["中金黄金", "山东黄金"]
    assert all(quote.name != "金盘科技" for quote in nonferrous_frontline)


def test_tickflow_market_provider_maps_grid_equipment_to_power_equipment_theme() -> None:
    quotes = [
        WatchlistQuote(symbol="000001.SH", name="上证指数", last_price=4100, pct_change=0.2, turnover_cny=1),
        WatchlistQuote(symbol="399006.SZ", name="创业板指", last_price=2200, pct_change=0.5, turnover_cny=1),
        WatchlistQuote(symbol="688676.SH", name="金盘科技", pct_change=10.5, turnover_cny=2_700_000_000),
        WatchlistQuote(symbol="300001.SZ", name="特锐德", pct_change=4.0, turnover_cny=680_000_000),
    ]
    provider = TickFlowMarketDataProvider(api_key="tk-test-local", base_url="https://api.tickflow.org", concept_provider=NoConceptProvider())
    provider.quote_provider = TrackingTickFlowProvider(
        quotes=quotes,
    )

    snapshot = provider.get_close_snapshot("2026-05-26")

    assert any(sector.name == "电力设备" for sector in snapshot.raw_sectors)
    assert all(sector.name != "电力" for sector in snapshot.raw_sectors)
    assert [quote.name for quote in provider.get_sector_frontline_stocks("电力设备")] == ["金盘科技"]


def test_tickflow_provider_rejects_missing_key() -> None:
    provider = TickFlowProvider(api_key="", base_url="https://api.tickflow.org")

    with pytest.raises(ProviderFallbackError, match="TICKFLOW_API_KEY"):
        provider.get_quotes(["600000.SH"])


def test_tickflow_provider_sanitizes_request_errors() -> None:
    leaked_key = "tk_secret_leak"
    provider = TickFlowProvider(
        api_key=leaked_key,
        base_url="https://api.tickflow.org",
        http_client=FakeClient(error=RuntimeError(f"boom {leaked_key}")),
    )

    with pytest.raises(ProviderFallbackError) as exc_info:
        provider.get_quotes(["600000.SH"])

    message = str(exc_info.value)
    assert "TickFlow 请求失败" in message
    assert leaked_key not in message


def test_tickflow_fallback_returns_fake_quotes_and_status() -> None:
    provider = FallbackTickFlowProvider(
        primary=TickFlowProvider(api_key="", base_url="https://api.tickflow.org"),
        fallback=FakeTickFlowProvider(),
        fallback_enabled=True,
    )

    quotes, status = provider.get_quotes_with_status(["600000.SH"])

    assert quotes[0].symbol == "600000.SH"
    assert status.provider == "tickflow"
    assert status.status == "fallback"
    assert status.fallback_used is True
    assert status.reason == "TICKFLOW_API_KEY 未配置"
