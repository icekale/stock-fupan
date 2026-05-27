from pathlib import Path

from app.config import Settings
from app.providers.factory import create_provider_bundle
from app.providers.review_sources import (
    AkShareReviewProvider,
    EastmoneyZtFpProvider,
    ReviewSourceAggregator,
    ReviewSourceResult,
    ThsFupanProvider,
    parse_10jqka_fupan_html,
    parse_eastmoney_ztfp_api_payload,
    parse_eastmoney_ztfp_html,
)


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
    assert any(
        stock.name == "生益电子" and stock.code == "688183" and stock.pct_change == 20.0
        for stock in result.hot_stocks
    )
    assert any("PCB概念股午后多数上扬" in note for note in result.market_notes)
    assert result.board_efficiency == "一般"


def test_parse_10jqka_fupan_splits_mixed_theme_notes_and_excludes_board_codes() -> None:
    html = """
    <strong>个股活跃程度及脉络</strong>
    <div>贵金属板块低开高走，招金黄金早盘涨停。PCB概念股午后多数上扬，生益电子20cm涨停，宝鼎科技涨停。</div>
    <strong class="mod_hd_s mt30">热门板块：</strong>
    <li><a>贵金属 881169</a><strong><span>5624.89</span><span>+222.22</span><span>+4.11%</span></strong></li>
    <strong class="mod_hd_s mt30">热门个股：</strong>
    <li><a>生益电子 688183</a><strong><span>132.10</span><span>+22.02</span><span>+20.00%</span></strong></li>
    """

    result = parse_10jqka_fupan_html(html, source_url="https://stock.10jqka.com.cn/fupan/")

    assert "贵金属板块低开高走，招金黄金早盘涨停" in result.market_notes
    assert "PCB概念股午后多数上扬，生益电子20cm涨停，宝鼎科技涨停" in result.market_notes
    assert not any(stock.code == "881169" for stock in result.hot_stocks)
    assert any(stock.name == "生益电子" and stock.code == "688183" for stock in result.hot_stocks)


def test_parse_eastmoney_ztfp_extracts_limit_up_themes_and_stock_mentions() -> None:
    html = (FIXTURES / "eastmoney_ztfp_sample.html").read_text(encoding="utf-8")

    result = parse_eastmoney_ztfp_html(html, source_url="https://stock.eastmoney.com/a/cztfp.html")

    assert result.source == "东方财富涨停复盘"
    assert result.status == "success"
    assert [theme.name for theme in result.themes] == ["有色金属", "PCB", "机器人"]
    assert any(stock.name == "生益电子" and stock.pct_change == 20.0 for stock in result.hot_stocks)
    assert any(stock.name == "中大力德" for stock in result.hot_stocks)
    assert result.market_notes[0].startswith("涨停复盘：有色金属")


def test_parse_eastmoney_ztfp_api_payload_extracts_current_limit_up_article() -> None:
    payload = {
        "code": "1",
        "data": {
            "list": [
                {
                    "title": "5月26日涨停复盘：64只股涨停 宝鼎科技14天9板",
                    "summary": "涨停个股数量方面，今日共计64股涨停。PCB概念股活跃，生益电子20CM涨停。",
                    "showTime": "2026-05-26 16:39:48",
                    "mediaName": "东方财富Choice数据",
                    "uniqueUrl": "http://stock.eastmoney.com/a/202605263749697543.html",
                },
                {
                    "title": "5月25日涨停复盘：128只股涨停",
                    "summary": "上一交易日内容。",
                    "showTime": "2026-05-25 16:15:27",
                    "mediaName": "东方财富Choice数据",
                    "uniqueUrl": "http://stock.eastmoney.com/a/202605253748168757.html",
                },
            ]
        },
    }

    result = parse_eastmoney_ztfp_api_payload(
        payload,
        source_url="https://stock.eastmoney.com/a/cztfp.html",
        trade_date="2026-05-26",
    )

    assert result.source == "东方财富涨停复盘"
    assert result.status == "success"
    assert result.trade_date == "2026-05-26"
    assert [theme.name for theme in result.themes] == ["PCB"]
    assert any(stock.name == "生益电子" and stock.pct_change == 20.0 for stock in result.hot_stocks)
    assert result.market_notes == [
        "5月26日涨停复盘：64只股涨停 宝鼎科技14天9板：涨停个股数量方面，今日共计64股涨停。PCB概念股活跃，生益电子20CM涨停。"
    ]


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


class FakeResponse:
    def __init__(
        self,
        text: str,
        content: bytes | None = None,
        json_payload: dict[str, object] | None = None,
    ) -> None:
        self.text = text
        self.content = content if content is not None else text.encode("utf-8")
        self.json_payload = json_payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        return self.json_payload or {}


class FakeHttpClient:
    def __init__(self, response: FakeResponse) -> None:
        self.response = response
        self.requests = []

    def get(self, url: str, **kwargs: object) -> FakeResponse:
        self.requests.append((url, kwargs))
        return self.response


class FakeSequenceHttpClient:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = responses
        self.requests = []

    def get(self, url: str, **kwargs: object) -> FakeResponse:
        self.requests.append((url, kwargs))
        return self.responses.pop(0)


def test_ths_provider_fetches_gbk_page_and_parses_review() -> None:
    html = (FIXTURES / "10jqka_fupan_sample.html").read_text(encoding="utf-8")
    client = FakeHttpClient(FakeResponse("", content=html.encode("gbk")))
    provider = ThsFupanProvider(http_client=client)

    result = provider("2026-05-26")

    assert result.source == "同花顺复盘"
    assert result.status == "success"
    assert "https://stock.10jqka.com.cn/fupan/" in client.requests[0][0]
    assert any(theme.name == "贵金属" for theme in result.themes)


def test_eastmoney_provider_prefers_list_api_for_current_limit_up_review() -> None:
    client = FakeHttpClient(
        FakeResponse(
            "",
            json_payload={
                "data": {
                    "list": [
                        {
                            "title": "5月26日涨停复盘：64只股涨停",
                            "summary": "PCB概念股活跃，生益电子20CM涨停。",
                            "showTime": "2026-05-26 16:39:48",
                        }
                    ]
                }
            },
        )
    )
    provider = EastmoneyZtFpProvider(http_client=client)

    result = provider("2026-05-26")

    assert result.source == "东方财富涨停复盘"
    assert result.status == "success"
    assert "https://np-listapi.eastmoney.com/comm/web/getNewsByColumns" in client.requests[0][0]
    assert any(theme.name == "PCB" for theme in result.themes)
    assert any(stock.name == "生益电子" for stock in result.hot_stocks)


def test_eastmoney_provider_falls_back_to_page_when_api_has_no_current_article() -> None:
    html = (FIXTURES / "eastmoney_ztfp_sample.html").read_text(encoding="utf-8")
    client = FakeSequenceHttpClient(
        [
            FakeResponse("", json_payload={"data": {"list": []}}),
            FakeResponse(html),
        ]
    )
    provider = EastmoneyZtFpProvider(http_client=client)

    result = provider("2026-05-26")

    assert result.source == "东方财富涨停复盘"
    assert result.status == "success"
    assert "https://stock.eastmoney.com/a/cztfp.html" in client.requests[1][0]
    assert any(theme.name == "PCB" for theme in result.themes)


def test_provider_bundle_includes_enabled_review_sources() -> None:
    settings = Settings(review_sources_enabled=True)

    bundle = create_provider_bundle(settings)

    assert bundle.review_source_provider is not None


def test_akshare_review_provider_extracts_concept_and_lhb_evidence() -> None:
    class FakeFrame:
        def __init__(self, rows: list[dict[str, object]]) -> None:
            self.rows = rows

        @property
        def empty(self) -> bool:
            return not self.rows

        def head(self, limit: int) -> "FakeFrame":
            return FakeFrame(self.rows[:limit])

        def iterrows(self):
            yield from enumerate(self.rows)

    class FakeAkShare:
        @staticmethod
        def stock_board_concept_name_em() -> FakeFrame:
            return FakeFrame(
                [
                    {"板块名称": "PCB", "涨跌幅": 4.2, "上涨家数": 38, "下跌家数": 9},
                    {"板块名称": "贵金属", "涨跌幅": 4.1, "上涨家数": 20, "下跌家数": 3},
                ]
            )

        @staticmethod
        def stock_lhb_detail_em(start_date: str, end_date: str) -> FakeFrame:
            assert start_date == "20260526"
            assert end_date == "20260526"
            return FakeFrame(
                [
                    {"股票名称": "生益电子", "股票代码": "688183", "涨跌幅": 20.0, "解读": "机构净买入"},
                    {"股票名称": "招金黄金", "股票代码": "600916", "涨跌幅": 10.0, "解读": "游资活跃"},
                ]
            )

    provider = AkShareReviewProvider(akshare_module=FakeAkShare)

    result = provider("2026-05-26")

    assert result.source == "AkShare概念/龙虎榜"
    assert result.status == "success"
    assert [theme.name for theme in result.themes] == ["PCB", "贵金属"]
    assert result.themes[0].pct_change == 4.2
    assert any(stock.name == "生益电子" and stock.code == "688183" for stock in result.hot_stocks)
    assert any("龙虎榜" in note for note in result.market_notes)
