from app.providers.a_stock_data import (
    AStockDragonTigerProvider,
    AStockIndustryRankProvider,
    AStockThsHotProvider,
    EastmoneyGlobalNewsProvider,
)


class FakeResponse:
    def __init__(self, payload: object, status_code: int = 200) -> None:
        self.payload = payload
        self.status_code = status_code
        self.text = "callback({})"

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self) -> object:
        return self.payload


class FakeClient:
    def __init__(self, response: FakeResponse) -> None:
        self.response = response
        self.requests: list[dict[str, object]] = []
        self.closed = False

    def get(self, url: str, **kwargs: object) -> FakeResponse:
        self.requests.append({"url": url, **kwargs})
        return self.response

    def close(self) -> None:
        self.closed = True


def test_a_stock_ths_hot_maps_hot_reason_payload() -> None:
    client = FakeClient(
        FakeResponse(
            {
                "errocode": 0,
                "data": [
                    {
                        "code": "300476",
                        "name": "胜宏科技",
                        "reason": "PCB+AI服务器",
                        "zhangfu": "12.34",
                    },
                    {
                        "code": "688017",
                        "name": "绿的谐波",
                        "reason": "机器人+减速器",
                        "zhangfu": "20.00",
                    },
                ],
            }
        )
    )
    provider = AStockThsHotProvider(http_client=client)

    result = provider("2026-05-26")

    assert result.source == "a-stock-data 同花顺热点"
    assert result.status == "success"
    assert {theme.name for theme in result.themes} >= {"PCB", "AI服务器", "机器人", "减速器"}
    assert result.hot_stocks[0].code == "300476"
    assert result.hot_stocks[0].pct_change == 12.34
    assert "胜宏科技: PCB+AI服务器" in result.market_notes


def test_a_stock_industry_rank_maps_eastmoney_payload() -> None:
    client = FakeClient(
        FakeResponse(
            {
                "data": {
                    "diff": [
                        {
                            "f14": "培育钻石",
                            "f3": 4.2,
                            "f12": "BK1023",
                            "f104": 11,
                            "f105": 5,
                            "f128": "恒盛能源",
                            "f140": "605580",
                            "f136": 10.0,
                        }
                    ]
                }
            }
        )
    )
    provider = AStockIndustryRankProvider(http_client=client, top_n=5)

    result = provider("2026-05-26")

    assert result.source == "a-stock-data 东财板块排名"
    assert result.status == "success"
    assert result.themes[0].name == "培育钻石"
    assert result.themes[0].pct_change == 4.2
    assert result.themes[0].stocks[0].name == "恒盛能源"
    assert result.themes[0].stocks[0].code == "605580"
    assert result.hot_stocks[0].name == "恒盛能源"
    assert "涨11跌5" in result.market_notes[0]
    assert client.requests[0]["url"] == "https://push2delay.eastmoney.com/api/qt/clist/get"
    assert client.requests[0]["params"]["fs"] == "m:90+t:3"
    assert client.requests[0]["params"]["fid"] == "f3"
    assert client.requests[0]["params"]["ut"] == "bd1d9ddb04089700cf9c27f6f7426281"


def test_eastmoney_global_news_filters_by_sector_keyword() -> None:
    client = FakeClient(
        FakeResponse(
            {
                "data": {
                    "fastNewsList": [
                        {
                            "title": "机器人产业链订单增长",
                            "summary": "减速器和伺服方向活跃",
                            "showTime": "2026-05-26 15:00:00",
                        },
                        {
                            "title": "海外宏观快讯",
                            "summary": "指数波动",
                            "showTime": "2026-05-26 14:00:00",
                        },
                    ]
                }
            }
        )
    )
    provider = EastmoneyGlobalNewsProvider(http_client=client, page_size=20)

    items = provider.search_sector_news("机器人", "2026-05-26")

    assert len(items) == 1
    assert items[0].title == "机器人产业链订单增长"
    assert items[0].matched_sector == "机器人"
    assert items[0].source == "东方财富"
    assert items[0].weight == 0.7


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
            if report_name == "RPT_BILLBOARD_DAILYDETAILSBUY":
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
            return FakeResponse(
                {
                    "success": True,
                    "result": {
                        "count": 2,
                        "data": [
                            {
                                "SECURITY_CODE": "002156",
                                "TRADE_DATE": "2026-06-03 00:00:00",
                                "OPERATEDEPT_NAME": "沪股通专用",
                                "BUY": 12000000,
                                "SELL": 32000000,
                                "NET": -20000000,
                            },
                            {
                                "SECURITY_CODE": "002156",
                                "TRADE_DATE": "2026-06-03 00:00:00",
                                "OPERATEDEPT_NAME": "机构专用",
                                "BUY": 10000000,
                                "SELL": 60000000,
                                "NET": -50000000,
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
    assert result.dragon_tiger.connect_net_buy_wan == 80845.9
    assert result.dragon_tiger.institution_net_buy_wan == 4924.3
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


def test_a_stock_dragon_tiger_returns_failed_when_market_rows_do_not_map() -> None:
    client = FakeClient(
        FakeResponse(
            {
                "success": True,
                "result": {
                    "count": 2,
                    "data": [
                        {
                            "TRADE_DATE": "2026-06-03 00:00:00",
                            "SECURITY_CODE": "",
                            "SECURITY_NAME_ABBR": "通富微电",
                            "BILLBOARD_NET_AMT": 1622415424.28,
                        },
                        {
                            "TRADE_DATE": "2026-06-03 00:00:00",
                            "SECURITY_CODE": "600487",
                            "SECURITY_NAME_ABBR": "",
                            "BILLBOARD_NET_AMT": 992629307.58,
                        },
                    ],
                },
            }
        )
    )
    provider = AStockDragonTigerProvider(http_client=client, sleep_seconds=0)

    result = provider("2026-06-03")

    assert result.status == "failed"
    assert result.reason == "未解析到东财龙虎榜股票"
    assert result.dragon_tiger is not None
    assert result.dragon_tiger.status == "failed"
