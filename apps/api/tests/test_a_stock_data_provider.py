from app.providers.a_stock_data import (
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
                            "f14": "半导体",
                            "f3": 4.2,
                            "f12": "BK1036",
                            "f104": 75,
                            "f105": 12,
                            "f140": "中芯国际",
                            "f136": 8.8,
                        }
                    ]
                }
            }
        )
    )
    provider = AStockIndustryRankProvider(http_client=client, top_n=5)

    result = provider("2026-05-26")

    assert result.source == "a-stock-data 东财行业排名"
    assert result.status == "success"
    assert result.themes[0].name == "半导体"
    assert result.themes[0].pct_change == 4.2
    assert result.hot_stocks[0].name == "中芯国际"
    assert "涨75跌12" in result.market_notes[0]


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
