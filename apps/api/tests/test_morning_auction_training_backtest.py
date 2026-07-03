from pathlib import Path

from app.services.morning_auction.artifacts import read_json
from app.services.morning_auction.backtest import backtest_top_n
from app.services.morning_auction.trainer import build_training_matrix, save_training_metadata


def test_build_training_matrix_orders_feature_columns() -> None:
    rows = [
        {"features": {"b": 2.0, "a": 1.0}, "main_label": True},
        {"features": {"a": None, "b": 4.0}, "main_label": False},
    ]

    matrix = build_training_matrix(rows)

    assert matrix.feature_names == ["a", "b"]
    assert matrix.x == [[1.0, 2.0], [0.0, 4.0]]
    assert matrix.y == [1, 0]


def test_training_metadata_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "metadata.json"

    save_training_metadata(
        path,
        model_version="model-v1",
        feature_version="features-v1",
        feature_names=["a", "b"],
        train_date_range=["2026-07-01", "2026-07-03"],
    )

    metadata = read_json(path)
    assert metadata["model_version"] == "model-v1"
    assert metadata["feature_names"] == ["a", "b"]


def test_backtest_top_n_reports_average_return_and_hit_rates() -> None:
    rows = [
        {
            "trade_date": "2026-07-01",
            "symbol": "600001.SH",
            "prob_3pct": 0.9,
            "open_to_close_return": 0.04,
            "main_label": True,
            "strong_label": False,
        },
        {
            "trade_date": "2026-07-01",
            "symbol": "600002.SH",
            "prob_3pct": 0.8,
            "open_to_close_return": -0.02,
            "main_label": False,
            "strong_label": False,
        },
        {
            "trade_date": "2026-07-02",
            "symbol": "600003.SH",
            "prob_3pct": 0.95,
            "open_to_close_return": 0.06,
            "main_label": True,
            "strong_label": True,
        },
    ]

    result = backtest_top_n(rows, top_n=1)

    assert result["top_n"] == 1
    assert result["trade_days"] == 2
    assert result["average_return"] == 0.05
    assert result["hit_3pct_rate"] == 1.0
    assert result["hit_5pct_rate"] == 0.5
