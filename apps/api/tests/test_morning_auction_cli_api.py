import json
from pathlib import Path

import pytest

from app.cli.morning_auction import main
from app.services.morning_auction.predictor import bucket_prediction
from app.services.morning_auction.schemas import MorningAuctionBucket


def test_bucket_prediction_assigns_selected_attack_watch_and_avoid() -> None:
    assert bucket_prediction(prob_3pct=0.82, strong_5pct_score=0.7, risk_flags=[]) == MorningAuctionBucket.SELECTED
    assert bucket_prediction(prob_3pct=0.7, strong_5pct_score=0.86, risk_flags=[]) == MorningAuctionBucket.ATTACK
    assert bucket_prediction(prob_3pct=0.45, strong_5pct_score=0.2, risk_flags=[]) == MorningAuctionBucket.WATCH
    assert bucket_prediction(prob_3pct=0.9, strong_5pct_score=0.9, risk_flags=["竞价涨幅过高"]) == MorningAuctionBucket.AVOID


def test_cli_backtest_reads_prediction_jsonl(tmp_path: Path, capsys) -> None:
    path = tmp_path / "predictions.jsonl"
    path.write_text(
        '{"trade_date":"2026-07-01","symbol":"600001.SH","prob_3pct":0.9,"open_to_close_return":0.04,"main_label":true,"strong_label":false}\n',
        encoding="utf-8",
    )

    exit_code = main(["backtest", "--predictions", str(path), "--top-n", "1"])

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["hit_3pct_rate"] == 1.0
    assert output["selected_count"] == 1
    assert output["top_n"] == 1


def test_cli_backtest_writes_output_json(tmp_path: Path, capsys) -> None:
    predictions_path = tmp_path / "predictions.jsonl"
    output_path = tmp_path / "backtest.json"
    predictions_path.write_text(
        '{"trade_date":"2026-07-01","symbol":"600001.SH","prob_3pct":0.9,"open_to_close_return":0.04,"main_label":true,"strong_label":false}\n',
        encoding="utf-8",
    )

    exit_code = main(
        [
            "backtest",
            "--predictions",
            str(predictions_path),
            "--top-n",
            "1",
            "--output",
            str(output_path),
        ]
    )

    stdout_payload = json.loads(capsys.readouterr().out)
    file_payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert file_payload == stdout_payload


def test_cli_backtest_rejects_missing_predictions_file(tmp_path: Path, capsys) -> None:
    missing_path = tmp_path / "missing.jsonl"

    with pytest.raises(SystemExit):
        main(["backtest", "--predictions", str(missing_path)])

    error = capsys.readouterr().err
    assert "predictions file does not exist" in error


def test_cli_backtest_rejects_non_positive_top_n(tmp_path: Path, capsys) -> None:
    path = tmp_path / "predictions.jsonl"
    path.write_text(
        '{"trade_date":"2026-07-01","symbol":"600001.SH","prob_3pct":0.9,"open_to_close_return":0.04,"main_label":true,"strong_label":false}\n',
        encoding="utf-8",
    )

    with pytest.raises(SystemExit):
        main(["backtest", "--predictions", str(path), "--top-n", "0"])

    error = capsys.readouterr().err
    assert "top-n must be positive" in error
