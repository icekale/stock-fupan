import json
import pickle
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from app.cli.morning_auction import main
from app.main import app
from app.services.morning_auction.artifacts import read_jsonl
from app.services.morning_auction.predictor import bucket_prediction
from app.services.morning_auction.schemas import MorningAuctionBucket
from app.services.morning_auction.trainer import save_training_metadata


class FakeProbabilityModel:
    def predict_proba(self, x: object) -> list[list[float]]:
        return [[0.75, 0.25] for _ in range(len(x))]


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


def test_cli_score_writes_prediction_jsonl(tmp_path: Path, capsys) -> None:
    dataset_path = tmp_path / "dataset.jsonl"
    model_path = tmp_path / "model.pkl"
    metadata_path = tmp_path / "metadata.json"
    output_path = tmp_path / "predictions.jsonl"
    dataset_path.write_text(
        '{"trade_date":"2026-07-01","symbol":"600001.SH","features":{"a":1.0},"main_label":true}\n',
        encoding="utf-8",
    )
    with model_path.open("wb") as handle:
        pickle.dump(FakeProbabilityModel(), handle)
    save_training_metadata(
        metadata_path,
        model_version="model-v1",
        feature_version="features-v1",
        feature_names=["a"],
        train_date_range=["2026-07-01", "2026-07-01"],
    )

    exit_code = main(
        [
            "score",
            "--dataset",
            str(dataset_path),
            "--model",
            str(model_path),
            "--metadata",
            str(metadata_path),
            "--output",
            str(output_path),
        ]
    )

    output = json.loads(capsys.readouterr().out)
    rows = read_jsonl(output_path)
    assert exit_code == 0
    assert output["rows"] == 1
    assert rows[0]["prob_3pct"] == 0.25


def test_morning_auction_predict_api_returns_run_payload() -> None:
    client = TestClient(app)

    response = client.post("/api/morning-auction/predict", json={"trade_date": "2026-07-03"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["trade_date"] == "2026-07-03"
    assert payload["model_version"] == "manual-cold-start"
    assert "items" in payload
