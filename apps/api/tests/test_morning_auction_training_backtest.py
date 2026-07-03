import pickle
from pathlib import Path

import pytest

from app.services.morning_auction.artifacts import read_json
from app.services.morning_auction.backtest import backtest_top_n
from app.services.morning_auction.features import FEATURE_VERSION
from app.services.morning_auction import trainer
from app.services.morning_auction.trainer import (
    build_training_matrix,
    save_training_metadata,
    train_lightgbm_model,
)
from app.services.morning_auction.scorer import score_rows_with_model


class FakeLGBMClassifier:
    latest: "FakeLGBMClassifier | None" = None

    def __init__(self, *, scale_pos_weight: float) -> None:
        self.scale_pos_weight = scale_pos_weight
        self.fit_args: tuple[list[list[float]], list[int], list[str]] | None = None
        FakeLGBMClassifier.latest = self

    def fit(self, x: list[list[float]], y: list[int], *, feature_name: list[str]) -> None:
        self.fit_args = (x, y, feature_name)


class FakeProbabilityModel:
    def __init__(self) -> None:
        self.seen_x: list[list[float]] | None = None

    def predict_proba(self, x: object) -> list[list[float]]:
        assert list(x.columns) == ["b", "a"]
        self.seen_x = x.to_numpy().tolist()
        return [[1 - row[0] / 10, row[0] / 10] for row in self.seen_x]


def test_build_training_matrix_orders_feature_columns() -> None:
    rows = [
        {"features": {"b": 2.0, "a": 1.0}, "main_label": True},
        {"features": {"a": None, "b": 4.0}, "main_label": False},
    ]

    matrix = build_training_matrix(rows)

    assert matrix.feature_names == ["a", "b"]
    assert matrix.x == [[1.0, 2.0], [0.0, 4.0]]
    assert matrix.y == [1, 0]


def test_build_training_matrix_can_use_configured_label_key() -> None:
    rows = [
        {"features": {"a": 1.0}, "main_label": False, "t1_close_label": True},
        {"features": {"a": 1.5}, "main_label": True, "t1_close_label": None},
        {"features": {"a": 2.0}, "main_label": True, "t1_close_label": False},
    ]

    matrix = build_training_matrix(rows, label_key="t1_close_label")

    assert matrix.x == [[1.0], [2.0]]
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


def test_train_lightgbm_model_writes_model_and_feature_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(trainer, "_load_lgbm_classifier", lambda: FakeLGBMClassifier)
    model_path = tmp_path / "model.pkl"
    metadata_path = tmp_path / "metadata.json"
    rows = [
        {
            "trade_date": "2026-07-03",
            "features": {"b": 2.0, "a": 1.0},
            "main_label": True,
        },
        {
            "trade_date": "2026-07-01",
            "features": {"a": None, "b": 4.0},
            "main_label": False,
        },
    ]

    result = train_lightgbm_model(rows, model_path, metadata_path)

    assert model_path.exists()
    metadata = read_json(metadata_path)
    assert metadata["feature_version"] == FEATURE_VERSION
    assert metadata["train_date_range"] == ["2026-07-01", "2026-07-03"]
    assert result["feature_names"] == ["a", "b"]
    assert result["positive_count"] == 1
    assert result["negative_count"] == 1
    assert FakeLGBMClassifier.latest is not None
    assert FakeLGBMClassifier.latest.scale_pos_weight == 1.0
    assert FakeLGBMClassifier.latest.fit_args == ([[1.0, 2.0], [0.0, 4.0]], [1, 0], ["a", "b"])


def test_score_rows_with_model_adds_probabilities_using_metadata_feature_order(tmp_path: Path) -> None:
    model_path = tmp_path / "model.pkl"
    metadata_path = tmp_path / "metadata.json"
    model = FakeProbabilityModel()
    with model_path.open("wb") as handle:
        pickle.dump(model, handle)
    save_training_metadata(
        metadata_path,
        model_version="model-v1",
        feature_version="features-v1",
        feature_names=["b", "a"],
        train_date_range=["2026-07-01", "2026-07-03"],
    )
    rows = [
        {"symbol": "600001.SH", "features": {"a": 1.0, "b": 2.0}},
        {"symbol": "600002.SH", "features": {"a": None, "b": 4.0}},
    ]

    scored = score_rows_with_model(rows, model_path=model_path, metadata_path=metadata_path)

    assert scored == [
        {"symbol": "600001.SH", "features": {"a": 1.0, "b": 2.0}, "prob_3pct": 0.2},
        {"symbol": "600002.SH", "features": {"a": None, "b": 4.0}, "prob_3pct": 0.4},
    ]
    assert rows[0].get("prob_3pct") is None


def test_train_lightgbm_model_surfaces_native_runtime_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def raise_runtime_error() -> type[FakeLGBMClassifier]:
        raise RuntimeError(
            "LightGBM is installed but cannot load native runtime dependencies; install libomp "
            "or configure the training environment."
        )

    monkeypatch.setattr(trainer, "_load_lgbm_classifier", raise_runtime_error)

    with pytest.raises(RuntimeError, match="install libomp or configure the training environment"):
        train_lightgbm_model(
            [{"trade_date": "2026-07-03", "features": {"a": 1.0}, "main_label": True}],
            tmp_path / "model.pkl",
            tmp_path / "metadata.json",
        )


def test_backtest_top_n_reports_return_hit_rate_and_payoff_metrics() -> None:
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

    result = backtest_top_n(rows, top_n=2)

    assert result["top_n"] == 2
    assert result["trade_days"] == 2
    assert result["selected_count"] == 3
    assert result["average_return"] == 0.026667
    assert result["hit_3pct_rate"] == 0.666667
    assert result["hit_5pct_rate"] == 0.333333
    assert result["win_rate"] == 0.666667
    assert result["loss_rate"] == 0.333333
    assert result["avg_win"] == 0.05
    assert result["avg_loss"] == 0.02
    assert result["payoff_ratio"] == 2.5
    assert result["profit_factor"] == 5.0
    assert result["breakeven_win_rate"] == 0.285714
    assert result["expectancy"] == 0.026667


def test_backtest_top_n_can_use_t1_return_key() -> None:
    rows = [
        {
            "trade_date": "2026-07-01",
            "prob_3pct": 0.9,
            "open_to_close_return": -0.01,
            "t1_close_return": 0.05,
        },
        {
            "trade_date": "2026-07-01",
            "prob_3pct": 0.8,
            "open_to_close_return": 0.08,
            "t1_close_return": -0.02,
        },
    ]

    result = backtest_top_n(rows, top_n=1, return_key="t1_close_return")

    assert result["average_return"] == 0.05
    assert result["win_rate"] == 1.0


def test_backtest_top_n_rejects_non_positive_top_n() -> None:
    with pytest.raises(ValueError, match="top_n must be positive"):
        backtest_top_n([], top_n=0)
