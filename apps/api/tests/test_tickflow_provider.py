import httpx
import pytest

from app.providers.market import ProviderFallbackError
from app.providers.tickflow import (
    FallbackTickFlowProvider,
    FakeTickFlowProvider,
    IndustryUniverse,
    TickFlowMarketDataProvider,
    TickFlowProvider,
    WatchlistQuote,
)


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
        universes: list[object],
        universe_details: dict[str, object],
    ) -> None:
        self.quotes = quotes
        self.universes = universes
        self.universe_details = universe_details
        self.detail_requests: list[str] = []

    def get_universe_quotes(self, universe_id: str) -> list[WatchlistQuote]:
        return self.quotes

    def get_quotes(self, symbols: list[str]) -> list[WatchlistQuote]:
        return [quote for quote in self.quotes if quote.symbol in symbols]

    def get_industry_universes(self) -> list[object]:
        return self.universes

    def get_universe(self, universe_id: str) -> object:
        self.detail_requests.append(universe_id)
        return self.universe_details[universe_id]

    def close(self) -> None:
        pass


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
    )

    snapshot = provider.get_close_snapshot("2026-05-27")

    assert snapshot.indices[0].name == "上证指数"
    assert snapshot.indices[0].pct_change == pytest.approx(-0.17)
    assert snapshot.breadth.up_count == 2
    assert snapshot.breadth.down_count == 1
    assert snapshot.turnover_cny == pytest.approx(163.5)
    assert snapshot.raw_sectors[0].name == "浦发银行"
    assert snapshot.raw_sectors[0].pct_change == pytest.approx(2.09)


def test_tickflow_market_provider_uses_full_market_and_industry_strength() -> None:
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


def test_tickflow_market_provider_groups_strong_stocks_into_themes() -> None:
    quotes = [
        WatchlistQuote(symbol="688183.SH", name="生益电子", pct_change=20, turnover_cny=9_700_000_000),
        WatchlistQuote(symbol="002463.SZ", name="沪电股份", pct_change=10.1, turnover_cny=1_200_000_000),
        WatchlistQuote(symbol="688335.SH", name="复洁科技", pct_change=19.98, turnover_cny=270_000_000),
        WatchlistQuote(symbol="300234.SZ", name="开尔新材", pct_change=14.65, turnover_cny=440_000_000),
        WatchlistQuote(symbol="600000.SH", name="浦发银行", pct_change=2.09, turnover_cny=1_350_000_000),
    ]

    provider = TickFlowMarketDataProvider(api_key="tk-test-local", base_url="https://api.tickflow.org")
    sectors = provider._strong_sectors_from_market(quotes)

    assert sectors[0].name == "PCB"
    assert sectors[0].limit_up_count == 2
    assert any(sector.name == "环保" for sector in sectors)
    assert all(sector.name != "浦发银行" for sector in sectors)


def test_tickflow_market_provider_does_not_classify_jinpan_as_nonferrous_by_single_character() -> None:
    quotes = [
        WatchlistQuote(symbol="688676.SH", name="金盘科技", pct_change=10.5, turnover_cny=2_700_000_000),
        WatchlistQuote(symbol="600489.SH", name="中金黄金", pct_change=10.0, turnover_cny=3_000_000_000),
        WatchlistQuote(symbol="600547.SH", name="山东黄金", pct_change=9.9, turnover_cny=2_000_000_000),
    ]

    provider = TickFlowMarketDataProvider(api_key="tk-test-local", base_url="https://api.tickflow.org")
    sectors = provider._strong_sectors_from_market(quotes)
    nonferrous = next(sector for sector in sectors if sector.name == "有色金属")

    assert nonferrous.limit_up_count == 2
    assert [quote.name for quote in provider.get_sector_frontline_stocks("有色金属")] == [
        "中金黄金",
        "山东黄金",
    ]


def test_tickflow_market_provider_exposes_frontline_stocks_for_ranked_sectors() -> None:
    quotes = [
        WatchlistQuote(symbol="688183.SH", name="生益电子", pct_change=20, turnover_cny=9_700_000_000),
        WatchlistQuote(symbol="002463.SZ", name="沪电股份", pct_change=10.1, turnover_cny=1_200_000_000),
        WatchlistQuote(symbol="688335.SH", name="复洁科技", pct_change=19.98, turnover_cny=270_000_000),
        WatchlistQuote(symbol="300234.SZ", name="开尔新材", pct_change=14.65, turnover_cny=440_000_000),
        WatchlistQuote(symbol="600000.SH", name="浦发银行", pct_change=2.09, turnover_cny=1_350_000_000),
    ]
    provider = TickFlowMarketDataProvider(api_key="tk-test-local", base_url="https://api.tickflow.org")

    sectors = provider._strong_sectors_from_market(quotes)
    pcb_frontline = provider.get_sector_frontline_stocks("PCB")

    assert sectors[0].name == "PCB"
    assert [quote.name for quote in pcb_frontline] == ["生益电子", "沪电股份"]
    assert all((quote.pct_change or 0) >= 9.8 for quote in pcb_frontline)


def test_tickflow_market_provider_uses_industry_members_only_to_refine_theme_frontline() -> None:
    quotes = [
        WatchlistQuote(symbol="000001.SH", name="上证指数", last_price=4100, pct_change=0.2, turnover_cny=1),
        WatchlistQuote(symbol="399006.SZ", name="创业板指", last_price=2200, pct_change=0.5, turnover_cny=1),
        WatchlistQuote(symbol="688676.SH", name="金盘科技", pct_change=11.04, turnover_cny=2_700_000_000),
        WatchlistQuote(symbol="600489.SH", name="中金黄金", pct_change=10.0, turnover_cny=3_000_000_000),
        WatchlistQuote(symbol="600547.SH", name="山东黄金", pct_change=9.9, turnover_cny=2_000_000_000),
        WatchlistQuote(symbol="603663.SH", name="三祥新材", pct_change=10.0, turnover_cny=1_200_000_000),
    ]
    universes = [
        IndustryUniverse("CN_Equity_SW3_230102", "黄金", 2),
        IndustryUniverse("CN_Equity_SW3_630201", "电网设备", 1),
        IndustryUniverse("CN_Equity_SW3_220503", "改性塑料", 1),
    ]
    provider = TickFlowMarketDataProvider(api_key="tk-test-local", base_url="https://api.tickflow.org")
    provider.quote_provider = TrackingTickFlowProvider(
        quotes=quotes,
        universes=universes,
        universe_details={
            "CN_Equity_SW3_230102": IndustryUniverse(
                "CN_Equity_SW3_230102",
                "黄金",
                2,
                ("600489.SH", "600547.SH"),
            ),
            "CN_Equity_SW3_630201": IndustryUniverse(
                "CN_Equity_SW3_630201",
                "电网设备",
                1,
                ("688676.SH",),
            ),
            "CN_Equity_SW3_220503": IndustryUniverse(
                "CN_Equity_SW3_220503",
                "改性塑料",
                1,
                ("603663.SH",),
            ),
        },
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
    provider = TickFlowMarketDataProvider(api_key="tk-test-local", base_url="https://api.tickflow.org")
    provider.quote_provider = TrackingTickFlowProvider(
        quotes=quotes,
        universes=[
            IndustryUniverse("CN_Equity_SW3_630201", "输变电设备", 2),
        ],
        universe_details={
            "CN_Equity_SW3_630201": IndustryUniverse(
                "CN_Equity_SW3_630201",
                "输变电设备",
                2,
                ("688676.SH", "300001.SZ"),
            )
        },
    )

    snapshot = provider.get_close_snapshot("2026-05-26")

    assert any(sector.name == "电力设备" for sector in snapshot.raw_sectors)
    assert all(sector.name != "电力" for sector in snapshot.raw_sectors)
    assert [quote.name for quote in provider.get_sector_frontline_stocks("电力设备")] == [
        "金盘科技",
        "特锐德",
    ]


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
