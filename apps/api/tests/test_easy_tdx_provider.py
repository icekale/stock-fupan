import pytest

from app.providers.easy_tdx import EasyTdxMarketDataProvider
from app.providers.market import ProviderFallbackError


class FrameStub:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows
        self.empty = not rows

    def to_dict(self, orient: str) -> list[dict[str, object]]:
        assert orient == "records"
        return self.rows


class FakeEasyTdxClient:
    def __init__(self) -> None:
        self.closed = False
        self.board_member_requests: list[str] = []

    def get_stock_quotes_list(self, *args: object, **kwargs: object) -> FrameStub:
        return FrameStub(
            [
                {
                    "market": 1,
                    "code": "688183",
                    "name": "生益电子",
                    "close": 132.1,
                    "pre_close": 110.08,
                    "amount": 9_700_000_000,
                    "turnover": 18.5,
                },
                {
                    "market": 0,
                    "code": "002463",
                    "name": "沪电股份",
                    "close": 52.6,
                    "pre_close": 47.77,
                    "amount": 1_200_000_000,
                    "turnover": 6.2,
                },
                {
                    "market": 0,
                    "code": "300234",
                    "name": "开尔新材",
                    "close": 18.35,
                    "pre_close": 17.2,
                    "amount": 440_000_000,
                    "turnover": 3.1,
                },
                {
                    "market": 1,
                    "code": "600000",
                    "name": "浦发银行",
                    "close": 9.27,
                    "pre_close": 9.08,
                    "amount": 1_350_000_000,
                    "turnover": 0.9,
                },
                {
                    "market": 0,
                    "code": "000001",
                    "name": "平安银行",
                    "close": 10.79,
                    "pre_close": 10.9,
                    "amount": 900_000_000,
                    "turnover": 0.8,
                },
            ]
        )

    def get_stock_quotes(self, symbols: list[tuple[object, str]]) -> FrameStub:
        return FrameStub(
            [
                {
                    "market": 1,
                    "code": "000001",
                    "name": "上证指数",
                    "close": 4145.37,
                    "pre_close": 4152.43,
                    "amount": 500_000_000_000,
                },
                {
                    "market": 0,
                    "code": "399006",
                    "name": "创业板指",
                    "close": 2600.12,
                    "pre_close": 2569.29,
                    "amount": 300_000_000_000,
                },
            ]
        )

    def get_board_ranking(self, *args: object, **kwargs: object) -> FrameStub:
        return FrameStub(
            [
                {
                    "code": "881001",
                    "name": "PCB",
                    "change_pct": 8.8,
                    "amount": 22_000_000_000,
                    "up_count": 42,
                    "down_count": 6,
                    "member_count": 58,
                    "main_net_amount": 1_250_000_000,
                },
                {
                    "code": "881002",
                    "name": "银行",
                    "change_pct": 0.6,
                    "amount": 18_000_000_000,
                    "up_count": 12,
                    "down_count": 25,
                    "member_count": 42,
                    "main_net_amount": -430_000_000,
                },
            ]
        )

    def get_board_members(self, board_symbol: str, **kwargs: object) -> FrameStub:
        self.board_member_requests.append(board_symbol)
        rows = {
            "881001": [
                {
                    "market": 1,
                    "code": "688183",
                    "name": "生益电子",
                    "close": 132.1,
                    "pre_close": 110.08,
                    "amount": 9_700_000_000,
                    "turnover": 18.5,
                },
                {
                    "market": 0,
                    "code": "002463",
                    "name": "沪电股份",
                    "close": 52.6,
                    "pre_close": 47.77,
                    "amount": 1_200_000_000,
                    "turnover": 6.2,
                },
            ],
            "881002": [
                {
                    "market": 1,
                    "code": "600000",
                    "name": "浦发银行",
                    "close": 9.27,
                    "pre_close": 9.08,
                    "amount": 1_350_000_000,
                    "turnover": 0.9,
                }
            ],
        }
        return FrameStub(rows.get(board_symbol, []))

    def close(self) -> None:
        self.closed = True


def test_easy_tdx_market_provider_builds_close_snapshot() -> None:
    client = FakeEasyTdxClient()
    provider = EasyTdxMarketDataProvider(client=client, board_top_n=2)

    snapshot = provider.get_close_snapshot("2026-06-02")

    assert snapshot.trade_date == "2026-06-02"
    assert snapshot.indices[0].name == "上证指数"
    assert snapshot.indices[0].code == "000001"
    assert snapshot.indices[0].pct_change == pytest.approx(-0.17, abs=0.01)
    assert snapshot.indices[1].name == "创业板指"
    assert snapshot.indices[1].pct_change == pytest.approx(1.2, abs=0.01)
    assert snapshot.breadth.up_count == 4
    assert snapshot.breadth.down_count == 1
    assert snapshot.breadth.limit_up_count == 2
    assert snapshot.turnover_cny == pytest.approx(135.9)
    assert snapshot.raw_sectors[0].name == "PCB"
    assert snapshot.raw_sectors[0].pct_change == pytest.approx(8.8)
    assert snapshot.raw_sectors[0].stock_up_ratio == pytest.approx(42 / 48)
    assert snapshot.raw_sectors[0].turnover_change == pytest.approx(1.0)
    assert "881001" in client.board_member_requests


def test_easy_tdx_market_provider_exposes_frontline_stocks() -> None:
    provider = EasyTdxMarketDataProvider(client=FakeEasyTdxClient(), board_top_n=2)
    provider.get_close_snapshot("2026-06-02")

    frontline = provider.get_sector_frontline_stocks("PCB")

    assert [quote.symbol for quote in frontline] == ["688183.SH", "002463.SZ"]
    assert frontline[0].name == "生益电子"
    assert frontline[0].pct_change == pytest.approx(20.0, abs=0.01)
    assert frontline[0].turnover_cny == 9_700_000_000
    assert frontline[0].turnover_rate == pytest.approx(18.5)
    assert frontline[0].capital_strength == "强"


def test_easy_tdx_market_provider_raises_when_data_is_insufficient() -> None:
    class EmptyClient(FakeEasyTdxClient):
        def get_stock_quotes_list(self, *args: object, **kwargs: object) -> FrameStub:
            return FrameStub([])

    provider = EasyTdxMarketDataProvider(client=EmptyClient())

    with pytest.raises(ProviderFallbackError, match="Easy TDX 行情数据不足"):
        provider.get_close_snapshot("2026-06-02")
