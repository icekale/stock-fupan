from pathlib import Path

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

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "hit_3pct_rate" in output
