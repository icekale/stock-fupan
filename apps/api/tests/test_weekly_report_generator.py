from pathlib import Path

from app.services.weekly_report_generator import AStockWeeklyDataClient, WeeklyReportGenerator


class FakeWeeklyMarketClient:
    provider_name = "a_stock"

    def get_weekly_market_data(self, start_date: str, end_date: str):
        assert start_date == "2026-05-25"
        assert end_date == "2026-05-29"
        return {
            "meta": {
                "source": "a-stock-data",
                "range": "2026-05-25..2026-05-29",
                "symbol_count": 4,
                "stock_rows": 4,
                "quote_count": 4,
                "instrument_count": 4,
            },
            "indices": {
                "000001.SH": {
                    "name": "上证指数",
                    "week_pct": -1.4,
                    "daily": [
                        {"date": "2026-05-25", "pct": 0.6, "amount": 1000, "close": 4152.0},
                        {"date": "2026-05-29", "pct": -0.7, "amount": 1200, "close": 4068.0},
                    ],
                },
                "399006.SZ": {
                    "name": "创业板指",
                    "week_pct": 1.58,
                    "daily": [
                        {"date": "2026-05-25", "pct": 1.1, "amount": 800, "close": 4021.0},
                        {"date": "2026-05-29", "pct": -2.1, "amount": 850, "close": 4037.0},
                    ],
                },
            },
            "breadth": {
                "2026-05-29": {
                    "count": 4,
                    "up_count": 1,
                    "down_count": 3,
                    "limit_up_count": 1,
                    "limit_down_count": 1,
                    "amount": 33300000000,
                    "median_pct": -2.2,
                }
            },
            "theme_stats": {
                "白酒/消费": {
                    "member_count": 2,
                    "avg_week_pct": 20.0,
                    "median_week_pct": 20.0,
                    "friday_avg_pct": 4.0,
                    "limit_up_days_sum": 1,
                    "amount_sum": 1000000000,
                    "top_week": [
                        {
                            "symbol": "000799.SZ",
                            "name": "酒鬼酒",
                            "week_pct": 15.0,
                            "friday_pct_from_kline": 10.0,
                            "amount_sum": 1200000000,
                            "turnover_rate": 8.8,
                            "limit_up_days": 1,
                        }
                    ],
                    "top_friday": [],
                },
                "电力": {
                    "member_count": 2,
                    "avg_week_pct": 18.0,
                    "median_week_pct": 18.0,
                    "friday_avg_pct": 8.0,
                    "limit_up_days_sum": 4,
                    "amount_sum": 23000000000,
                    "top_week": [
                        {
                            "symbol": "600726.SH",
                            "name": "华电能源",
                            "week_pct": 61.05,
                            "friday_pct_from_kline": 9.99,
                            "amount_sum": 7360000000,
                            "turnover_rate": 2.26,
                            "limit_up_days": 5,
                        },
                        {
                            "symbol": "000539.SZ",
                            "name": "粤电力Ａ",
                            "week_pct": 35.57,
                            "friday_pct_from_kline": 10.04,
                            "amount_sum": 4680000000,
                            "turnover_rate": 4.56,
                            "limit_up_days": 3,
                        },
                    ],
                    "top_friday": [
                        {
                            "symbol": "301439.SZ",
                            "name": "泓淋电力",
                            "week_pct": 15.51,
                            "friday_pct_from_kline": 19.99,
                            "friday_amount": 237000000,
                            "turnover_rate": 6.61,
                            "limit_up_days": 1,
                        }
                    ],
                },
                "半导体/先进封装": {
                    "member_count": 2,
                    "avg_week_pct": -3.9,
                    "median_week_pct": -7.1,
                    "friday_avg_pct": -5.8,
                    "limit_up_days_sum": 1,
                    "amount_sum": 10000000000,
                    "top_week": [
                        {
                            "symbol": "688347.SH",
                            "name": "华虹公司",
                            "week_pct": 29.33,
                            "friday_pct_from_kline": -5.2,
                            "amount_sum": 5000000000,
                            "turnover_rate": 9.62,
                            "limit_up_days": 2,
                        }
                    ],
                    "top_friday": [],
                },
            },
            "top_week": [],
            "top_friday": [],
        }


class FakeWeeklyNewsProvider:
    provider_name = "anspire"

    def search_sector_news(self, sector_name: str, trade_date: str):
        return [
            type(
                "News",
                (),
                {
                    "title": f"{sector_name}催化",
                    "summary": "南方电网负荷创新高，算电协同强化电力主线。",
                    "url": "https://example.com/news",
                    "source": "Anspire",
                    "model_dump": lambda self, mode="json": {
                        "title": self.title,
                        "summary": self.summary,
                        "url": self.url,
                        "source": self.source,
                    },
                },
            )()
        ]


class WeeklyAStockResponse:
    def __init__(self, payload: object | None = None, text: str = "") -> None:
        self.payload = payload
        self.text = text

    def raise_for_status(self) -> None:
        pass

    def json(self) -> object:
        return self.payload


class WeeklyAStockHttpClient:
    def __init__(self) -> None:
        self.requests: list[str] = []

    def get(self, url: str, **kwargs: object) -> WeeklyAStockResponse:
        self.requests.append(url)
        if "qt.gtimg.cn" in url:
            return WeeklyAStockResponse(
                text=(
                    'v_sh600726="1~华电能源~600726~7.20~6.80~6.90~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0.40~5.88~7.25~6.75~0~0~736000~2.26~0~0~0~0~0~0~0~0~0~0~1.22~0~0~0";\n'
                    'v_sz000539="51~粤电力Ａ~000539~6.60~6.20~6.30~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0.40~6.45~6.65~6.10~0~0~468000~4.56~0~0~0~0~0~0~0~0~0~0~1.55~0~0~0";\n'
                    'v_sh000001="1~上证指数~000001~4068.00~4100.00~4110.00~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~-32.00~-0.78~4120.00~4050.00~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0";\n'
                    'v_sz399006="51~创业板指~399006~4037.00~4000.00~4010.00~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~37.00~0.93~4050.00~3990.00~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0";'
                )
            )
        params = kwargs.get("params")
        code = params["code"] if isinstance(params, dict) else ""
        payloads = {
            "600726": "2026-05-25,4.47,5.00,5.10,4.40,1000,1200000000;2026-05-29,6.55,7.20,7.20,6.40,2000,7360000000",
            "000539": "2026-05-25,4.87,5.20,5.30,4.80,1000,1000000000;2026-05-29,6.00,6.60,6.60,5.90,1500,4680000000",
            "000001": "2026-05-25,4152.0,4120.0,4160.0,4100.0,0,100000000000;2026-05-29,4100.0,4068.0,4120.0,4050.0,0,120000000000",
            "399006": "2026-05-25,4021.0,4070.0,4080.0,4000.0,0,80000000000;2026-05-29,4120.0,4037.0,4140.0,4000.0,0,85000000000",
        }
        return WeeklyAStockResponse(
            payload={
                "Result": {
                    "newMarketData": {
                        "keys": ["time", "open", "close", "high", "low", "volume", "amount"],
                        "marketData": payloads.get(code, ""),
                    }
                }
            }
        )

    def close(self) -> None:
        pass


def test_a_stock_weekly_client_builds_summary_from_public_sources() -> None:
    client = AStockWeeklyDataClient(
        http_client=WeeklyAStockHttpClient(),
        symbols=(("600726.SH", "华电能源"), ("000539.SZ", "粤电力Ａ")),
        index_symbols=(("000001.SH", "上证指数"), ("399006.SZ", "创业板指")),
    )

    summary = client.get_weekly_market_data("2026-05-25", "2026-05-29")

    assert summary["meta"]["source"] == "a-stock-data"
    assert summary["meta"]["symbol_count"] == 2
    assert summary["meta"]["stock_rows"] == 2
    assert summary["indices"]["000001.SH"]["name"] == "上证指数"
    assert summary["breadth"]["2026-05-29"]["up_count"] == 2
    assert summary["theme_stats"]["电力"]["top_week"][0]["name"] == "华电能源"


def test_weekly_generator_writes_real_data_assets(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.weekly_report_generator.export_png",
        lambda html_path, output_path: output_path.write_bytes(b"png"),
    )
    monkeypatch.setattr(
        "app.services.weekly_report_generator.export_pdf",
        lambda html_path, output_path: output_path.write_bytes(b"pdf"),
    )
    generator = WeeklyReportGenerator(
        reports_root=tmp_path,
        market_client=FakeWeeklyMarketClient(),
        news_provider=FakeWeeklyNewsProvider(),
    )

    result = generator.generate_weekly_report("2026-05-25", "2026-05-29")

    assert result.trade_date == "2026-05-25_2026-05-29"
    assert result.assets.root == tmp_path / "2026-05-25_2026-05-29" / "weekly" / "v001"
    assert result.assets.report_html.exists()
    assert result.assets.report_png.read_bytes() == b"png"
    assert result.assets.report_pdf.read_bytes() == b"pdf"
    assert (result.assets.root / "2026-05-25_2026-05-29-周报复盘.html").exists()
    html = result.assets.report_html.read_text(encoding="utf-8")
    assert "2026-05-25 至 2026-05-29 周报复盘" in html
    assert "a-stock-data 覆盖 4/4 只" in html
    assert "电力" in html
    assert "华电能源" in html
    assert "最强主线：电力" in html
    assert "下周观察条件" in html
    assert "fake" not in html.lower()
    assert result.summary.get("algorithm_versions", {}).get("weekly_report") == "weekly_report_daily_dimensions_v2"
    assert result.validation_errors == []


def test_weekly_report_uses_daily_review_analysis_dimensions(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.weekly_report_generator.export_png",
        lambda html_path, output_path: output_path.write_bytes(b"png"),
    )
    monkeypatch.setattr(
        "app.services.weekly_report_generator.export_pdf",
        lambda html_path, output_path: output_path.write_bytes(b"pdf"),
    )
    generator = WeeklyReportGenerator(
        reports_root=tmp_path,
        market_client=FakeWeeklyMarketClient(),
        news_provider=FakeWeeklyNewsProvider(),
    )

    result = generator.generate_weekly_report("2026-05-25", "2026-05-29")
    html = result.assets.report_html.read_text(encoding="utf-8")

    expected_sections = [
        "本周核心结论",
        "指数与市场情绪",
        "本周预判验证",
        "板块详细分析",
        "资金轮动路径",
        "板块持续性排序",
        "下周操作思路",
        "周末 / 下周消息梳理",
        "去弱留强排序",
        "最实战的结论",
        "指数中期走势研判",
    ]
    for section in expected_sections:
        assert section in html

    assert "阶段" in html
    assert "周内路径" in html
    assert "前排股" in html
    assert "资金强度" in html
    assert "催化逻辑" in html
    assert "下周条件" in html
    assert "半导体/先进封装" in html
    assert "高位分歧" in html
    assert "电力" in html
    assert "主线延续" in html
