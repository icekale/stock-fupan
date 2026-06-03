import json
import subprocess
import sys
from pathlib import Path
from textwrap import dedent


def test_thsdk_probe_reports_available_dependency_without_live_query() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "probe_thsdk.py"

    result = subprocess.run(
        [sys.executable, str(script_path), "--skip-live"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["provider"] == "thsdk"
    assert payload["status"] == "available"
    assert payload["next_step"] == "去掉 --skip-live 执行真实接口探测。"
    assert "Traceback" not in result.stderr


def test_thsdk_probe_summarizes_live_checks_with_fake_module(tmp_path: Path) -> None:
    fake_package = tmp_path / "thsdk"
    fake_package.mkdir()
    (fake_package / "__init__.py").write_text(
        dedent(
            """
            class Response:
                def __init__(self, data):
                    self.success = True
                    self.data = data
                    self.extra = {"ServerDelay": 0}
                    self.error = ""


            class THS:
                def __enter__(self):
                    return self

                def __exit__(self, exc_type, exc_value, traceback):
                    return None

                def complete_ths_code(self, symbol):
                    return Response([{"THSCODE": "USZA300033"}])

                def wencai_nlp(self, keyword):
                    return Response([{"股票简称": "春秋电子", "涨停[20260529]": "涨停"}])

                def ths_concept(self):
                    return Response([{"代码": "URFI885000", "名称": "机器人概念"}])

                def market_data_block(self, code):
                    return Response([{"代码": code, "名称": "半导体", "涨停家数": 3}])

                def klines(self, code, count):
                    return Response([{"代码": code, "收盘价": 10.5}])

                def intraday_data(self, code):
                    return Response([{"代码": code, "价格": 10.7}])
            """
        ),
        encoding="utf-8",
    )
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "probe_thsdk.py"

    result = subprocess.run(
        [sys.executable, str(script_path)],
        check=False,
        capture_output=True,
        text=True,
        env={"PYTHONPATH": str(tmp_path)},
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "success"
    assert payload["summary"] == {
        "success_count": 6,
        "total_count": 6,
        "recommended_for_report": True,
    }
    assert {item["name"] for item in payload["checks"]} == {
        "complete_ths_code",
        "wencai_nlp",
        "ths_concept",
        "market_data_block",
        "klines",
        "intraday_data",
    }
