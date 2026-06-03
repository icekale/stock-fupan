from app.providers.thsdk import ThsdkProvider, ThsdkProbeResult


class FakeResponse:
    success = True
    extra = {"ServerDelay": 0}
    error = ""

    def __init__(self, data: list[dict[str, object]]) -> None:
        self.data = data


class FakeThsClient:
    def __enter__(self) -> "FakeThsClient":
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        return None

    def complete_ths_code(self, symbol: str) -> FakeResponse:
        return FakeResponse([{"THSCODE": "USZA300033", "symbol": symbol}])

    def wencai_nlp(self, keyword: str) -> FakeResponse:
        if "连板" in keyword:
            return FakeResponse(
                [
                    {
                        "股票简称": "天健集团",
                        "股票代码": "000090.SZ",
                        "所属概念": "人工智能;机器人概念;深圳国企改革",
                        "连续涨停天数[20260529]": 2,
                    }
                ]
            )
        return FakeResponse(
            [
                {
                    "股票简称": "*ST美丽",
                    "股票代码": "000010.SZ",
                    "所属概念": "ST板块;新型城镇化",
                    "涨停[20260529]": "涨停",
                },
                {
                    "股票简称": "春秋电子",
                    "股票代码": "603890.SH",
                    "所属概念": "AI PC;人形机器人;机器人概念",
                    "涨停[20260529]": "涨停",
                }
            ]
        )

    def ths_concept(self) -> FakeResponse:
        return FakeResponse([{"代码": "URFI885000", "名称": "机器人概念"}])

    def market_data_block(self, code: str) -> FakeResponse:
        return FakeResponse([{"代码": code, "名称": "半导体"}])

    def klines(self, code: str, count: int) -> FakeResponse:
        return FakeResponse([{"代码": code, "count": count}])

    def intraday_data(self, code: str) -> FakeResponse:
        return FakeResponse([{"代码": code, "价格": 10.7}])


def test_thsdk_provider_probe_summarizes_experimental_capabilities() -> None:
    provider = ThsdkProvider(client_factory=FakeThsClient)

    result = provider.probe(keyword="今日涨停", symbol="300033")

    assert isinstance(result, ThsdkProbeResult)
    assert result.status == "success"
    assert result.summary == {
        "success_count": 6,
        "total_count": 6,
        "recommended_for_report": True,
    }
    assert {item["name"] for item in result.checks} == {
        "complete_ths_code",
        "wencai_nlp",
        "ths_concept",
        "market_data_block",
        "klines",
        "intraday_data",
    }


def test_thsdk_provider_reports_missing_dependency() -> None:
    provider = ThsdkProvider(client_factory=None)

    result = provider.check_available()

    assert result.status == "unavailable"
    assert result.reason == "THSDK 未安装"


def test_thsdk_provider_builds_review_source_result_from_wencai_and_concepts() -> None:
    provider = ThsdkProvider(client_factory=FakeThsClient)

    result = provider.collect_review_evidence("2026-05-29")

    assert result.source == "THSDK"
    assert result.source_url == "thsdk://local"
    assert result.status == "success"
    assert result.trade_date == "2026-05-29"
    assert any(theme.name == "机器人概念" and theme.source == "THSDK" for theme in result.themes)
    assert any(stock.name == "春秋电子" and stock.source == "THSDK" for stock in result.hot_stocks)
    assert any(stock.name == "天健集团" and "2连板" in stock.note for stock in result.hot_stocks)
    assert not any(stock.name == "*ST美丽" for stock in result.hot_stocks)
    assert not any(theme.name == "ST板块" for theme in result.themes)
    assert any("问财今日涨停返回" in note for note in result.market_notes)
