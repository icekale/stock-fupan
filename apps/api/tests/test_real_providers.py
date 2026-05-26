from datetime import date

import pandas as pd
import pytest

from app.providers.market import (
    AkShareMarketDataProvider,
    FakeMarketDataProvider,
    FallbackMarketDataProvider,
    MarketCloseSnapshot,
    ProviderFallbackError,
)
from app.providers.market import ProviderStatus
from app.providers.news import AnspireNewsProvider, FakeNewsProvider, FallbackNewsProvider, SectorNewsResult
from app.schemas.report import NewsItem


def test_provider_status_serializes_for_snapshot() -> None:
    status = ProviderStatus(
        provider="akshare",
        status="fallback",
        fallback_used=True,
        reason="AkShare v0.2 暂不支持历史日期",
    )

    assert status.model_dump(mode="json") == {
        "provider": "akshare",
        "status": "fallback",
        "fallback_used": True,
        "reason": "AkShare v0.2 暂不支持历史日期",
    }


def test_sector_news_result_keeps_sector_status_and_items() -> None:
    item = NewsItem(
        title="机器人产业链催化增强",
        url="https://example.com/news",
        source="示例财经",
        summary="机器人方向出现政策和产业消息共振。",
        matched_sector="机器人",
        weight=0.8,
    )
    result = SectorNewsResult(
        sector="机器人",
        items=[item],
        status=ProviderStatus(
            provider="anspire",
            status="success",
            fallback_used=False,
            reason=None,
        ),
    )

    assert result.sector == "机器人"
    assert result.items == [item]
    assert result.status.provider == "anspire"
    assert result.status.status == "success"


class BrokenMarketProvider:
    provider_name = "akshare"

    def get_close_snapshot(self, trade_date: str) -> MarketCloseSnapshot:
        raise ProviderFallbackError("AkShare v0.2 暂不支持历史日期")


class BrokenNewsProvider:
    provider_name = "anspire"

    def search_sector_news(self, sector_name: str, trade_date: str) -> list[NewsItem]:
        raise ProviderFallbackError("ANSPIRE_API_KEY 未配置")


def test_market_fallback_returns_fake_snapshot_and_reason() -> None:
    provider = FallbackMarketDataProvider(
        primary=BrokenMarketProvider(),
        fallback=FakeMarketDataProvider(),
        fallback_enabled=True,
    )

    snapshot, status = provider.get_close_snapshot_with_status("2026-05-25")

    assert snapshot.raw_sectors[0].name == "机器人"
    assert status.provider == "akshare"
    assert status.status == "fallback"
    assert status.fallback_used is True
    assert status.reason == "AkShare v0.2 暂不支持历史日期"


def test_market_fallback_can_raise_when_disabled() -> None:
    provider = FallbackMarketDataProvider(
        primary=BrokenMarketProvider(),
        fallback=FakeMarketDataProvider(),
        fallback_enabled=False,
    )

    with pytest.raises(ProviderFallbackError):
        provider.get_close_snapshot_with_status("2026-05-25")


def test_news_fallback_returns_fake_items_and_reason() -> None:
    provider = FallbackNewsProvider(
        primary=BrokenNewsProvider(),
        fallback=FakeNewsProvider(),
        fallback_enabled=True,
    )

    result = provider.search_sector_news_with_status("机器人", "2026-05-26")

    assert result.items[0].matched_sector == "机器人"
    assert result.status.provider == "anspire"
    assert result.status.status == "fallback"
    assert result.status.fallback_used is True
    assert result.status.reason == "ANSPIRE_API_KEY 未配置"


def test_akshare_provider_builds_current_market_snapshot(monkeypatch) -> None:
    class FakeAkshare:
        @staticmethod
        def stock_zh_index_spot_em() -> pd.DataFrame:
            return pd.DataFrame(
                [
                    {"名称": "上证指数", "代码": "000001", "最新价": 3100.5, "涨跌幅": 1.2},
                    {"名称": "创业板指", "代码": "399006", "最新价": 1950.2, "涨跌幅": 2.1},
                ]
            )

        @staticmethod
        def stock_zh_a_spot_em() -> pd.DataFrame:
            return pd.DataFrame(
                [
                    {"代码": "000001", "名称": "平安银行", "涨跌幅": 1.0, "成交额": 100000000},
                    {"代码": "000002", "名称": "万科A", "涨跌幅": -1.0, "成交额": 200000000},
                    {"代码": "000003", "名称": "涨停股", "涨跌幅": 10.0, "成交额": 300000000},
                    {"代码": "000004", "名称": "跌停股", "涨跌幅": -10.0, "成交额": 400000000},
                ]
            )

        @staticmethod
        def stock_board_industry_name_em() -> pd.DataFrame:
            return pd.DataFrame(
                [
                    {"板块名称": "机器人", "涨跌幅": 5.88, "上涨家数": 41, "下跌家数": 9, "总成交额": 35000000000},
                    {"板块名称": "PCB", "涨跌幅": 3.6, "上涨家数": 35, "下跌家数": 15, "总成交额": 22000000000},
                ]
            )

    provider = AkShareMarketDataProvider(
        akshare_module=FakeAkshare,
        today=date(2026, 5, 26),
    )

    snapshot = provider.get_close_snapshot("2026-05-26")

    assert snapshot.indices[0].name == "上证指数"
    assert snapshot.breadth.up_count == 2
    assert snapshot.breadth.down_count == 2
    assert snapshot.breadth.limit_up_count == 1
    assert snapshot.breadth.limit_down_count == 1
    assert snapshot.turnover_cny == 10.0
    assert snapshot.raw_sectors[0].name == "机器人"
    assert snapshot.raw_sectors[0].stock_up_ratio == 0.82


def test_akshare_provider_rejects_historical_date() -> None:
    provider = AkShareMarketDataProvider(today=date(2026, 5, 26))

    with pytest.raises(ProviderFallbackError, match="历史日期"):
        provider.get_close_snapshot("2026-05-25")


def _valid_index_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"名称": "上证指数", "代码": "000001", "最新价": 3100.5, "涨跌幅": 1.2},
            {"名称": "创业板指", "代码": "399006", "最新价": 1950.2, "涨跌幅": 2.1},
        ]
    )


def _valid_stock_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"代码": "000001", "名称": "平安银行", "涨跌幅": 1.0, "成交额": 100000000},
            {"代码": "000002", "名称": "万科A", "涨跌幅": -1.0, "成交额": 200000000},
        ]
    )


def _valid_sector_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"板块名称": "机器人", "涨跌幅": 5.88, "上涨家数": 41, "下跌家数": 9},
        ]
    )


class ConfigurableFakeAkshare:
    index_df = _valid_index_df()
    stock_df = _valid_stock_df()
    sector_df = _valid_sector_df()

    @classmethod
    def stock_zh_index_spot_em(cls) -> pd.DataFrame:
        return cls.index_df

    @classmethod
    def stock_zh_a_spot_em(cls) -> pd.DataFrame:
        return cls.stock_df

    @classmethod
    def stock_board_industry_name_em(cls) -> pd.DataFrame:
        return cls.sector_df


@pytest.mark.parametrize(
    ("index_df", "stock_df", "sector_df"),
    [
        (pd.DataFrame(), _valid_stock_df(), _valid_sector_df()),
        (_valid_index_df(), pd.DataFrame(), _valid_sector_df()),
        (_valid_index_df(), _valid_stock_df(), pd.DataFrame()),
    ],
)
def test_akshare_provider_raises_for_empty_dataframes(index_df, stock_df, sector_df) -> None:
    class FakeAkshare(ConfigurableFakeAkshare):
        pass

    FakeAkshare.index_df = index_df
    FakeAkshare.stock_df = stock_df
    FakeAkshare.sector_df = sector_df
    provider = AkShareMarketDataProvider(akshare_module=FakeAkshare, today=date(2026, 5, 26))

    with pytest.raises(ProviderFallbackError, match="空数据"):
        provider.get_close_snapshot("2026-05-26")


@pytest.mark.parametrize(
    ("stock_df", "sector_df"),
    [
        (_valid_stock_df().drop(columns=["涨跌幅"]), _valid_sector_df()),
        (_valid_stock_df().drop(columns=["成交额"]), _valid_sector_df()),
        (_valid_stock_df(), _valid_sector_df().drop(columns=["上涨家数"])),
        (_valid_stock_df(), _valid_sector_df().drop(columns=["下跌家数"])),
        (_valid_stock_df(), _valid_sector_df().drop(columns=["涨跌幅"])),
    ],
)
def test_akshare_provider_raises_for_missing_required_columns(stock_df, sector_df) -> None:
    class FakeAkshare(ConfigurableFakeAkshare):
        pass

    FakeAkshare.index_df = _valid_index_df()
    FakeAkshare.stock_df = stock_df
    FakeAkshare.sector_df = sector_df
    provider = AkShareMarketDataProvider(akshare_module=FakeAkshare, today=date(2026, 5, 26))

    with pytest.raises(ProviderFallbackError, match="缺少字段"):
        provider.get_close_snapshot("2026-05-26")


@pytest.mark.parametrize("bad_value", ["not-a-number", float("nan"), float("inf")])
@pytest.mark.parametrize(
    ("frame_name", "column_name"),
    [
        ("stock", "涨跌幅"),
        ("stock", "成交额"),
        ("sector", "上涨家数"),
        ("sector", "下跌家数"),
        ("sector", "涨跌幅"),
    ],
)
def test_akshare_provider_raises_for_invalid_required_numbers(bad_value, frame_name, column_name) -> None:
    stock_df = _valid_stock_df()
    sector_df = _valid_sector_df()
    if frame_name == "stock":
        stock_df[column_name] = stock_df[column_name].astype(object)
        stock_df.loc[0, column_name] = bad_value
    else:
        sector_df[column_name] = sector_df[column_name].astype(object)
        sector_df.loc[0, column_name] = bad_value

    class FakeAkshare(ConfigurableFakeAkshare):
        pass

    FakeAkshare.index_df = _valid_index_df()
    FakeAkshare.stock_df = stock_df
    FakeAkshare.sector_df = sector_df
    provider = AkShareMarketDataProvider(akshare_module=FakeAkshare, today=date(2026, 5, 26))

    with pytest.raises(ProviderFallbackError, match="非数字字段"):
        provider.get_close_snapshot("2026-05-26")


class FakeResponse:
    def __init__(self, status_code: int, payload: dict[str, object]) -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = str(payload)

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise ProviderFallbackError(f"Anspire HTTP {self.status_code}")

    def json(self) -> dict[str, object]:
        return self._payload


class FakeHttpClient:
    def __init__(self, response: FakeResponse) -> None:
        self.response = response
        self.last_headers: dict[str, str] = {}
        self.last_params: dict[str, object] = {}

    def get(self, _url: str, headers: dict[str, str], params: dict[str, object], timeout: float) -> FakeResponse:
        self.last_headers = headers
        self.last_params = params
        return self.response


def test_anspire_provider_maps_results_to_news_items() -> None:
    client = FakeHttpClient(
        FakeResponse(
            200,
            {
                "data": [
                    {
                        "title": "机器人产业链催化增强",
                        "url": "https://example.com/robot",
                        "source": "财联社",
                        "summary": "机器人方向出现政策催化。",
                        "published_at": "2026-05-26T14:30:00+08:00",
                    }
                ]
            },
        )
    )
    provider = AnspireNewsProvider(
        api_key="secret-key",
        base_url="https://plugin.anspire.cn/api/ntsearch/search",
        top_k=5,
        lookback_hours=36,
        http_client=client,
    )

    items = provider.search_sector_news("机器人", "2026-05-26")

    assert client.last_headers["Authorization"] == "Bearer secret-key"
    assert client.last_params["query"] == "机器人 A股"
    assert client.last_params["top_k"] == 5
    assert items[0].title == "机器人产业链催化增强"
    assert items[0].source == "财联社"
    assert items[0].matched_sector == "机器人"
    assert items[0].weight == 0.9


def test_anspire_provider_rejects_missing_key() -> None:
    provider = AnspireNewsProvider(api_key="")

    with pytest.raises(ProviderFallbackError, match="ANSPIRE_API_KEY"):
        provider.search_sector_news("机器人", "2026-05-26")


def test_anspire_provider_rejects_empty_results() -> None:
    provider = AnspireNewsProvider(
        api_key="secret-key",
        http_client=FakeHttpClient(FakeResponse(200, {"data": []})),
    )

    with pytest.raises(ProviderFallbackError, match="无结果"):
        provider.search_sector_news("机器人", "2026-05-26")
