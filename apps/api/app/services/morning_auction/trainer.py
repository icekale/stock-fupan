from __future__ import annotations

import pickle
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from app.services.morning_auction import MORNING_AUCTION_VERSION
from app.services.morning_auction.artifacts import ensure_parent, write_json
from app.services.morning_auction.features import FEATURE_VERSION


@dataclass(frozen=True)
class TrainingMatrix:
    x: list[list[float]]
    y: list[int]
    feature_names: list[str]


def build_training_matrix(rows: Sequence[dict[str, object]]) -> TrainingMatrix:
    feature_names = sorted(
        {
            str(name)
            for row in rows
            for name in _features(row).keys()
        }
    )
    x = [
        [_feature_value(_features(row).get(feature_name)) for feature_name in feature_names]
        for row in rows
    ]
    y = [1 if row.get("main_label") else 0 for row in rows]
    return TrainingMatrix(x=x, y=y, feature_names=feature_names)


def train_lightgbm_model(
    rows: Sequence[dict[str, object]],
    model_path: Path,
    metadata_path: Path,
) -> dict[str, object]:
    lgbm_classifier = _load_lgbm_classifier()
    matrix = build_training_matrix(rows)
    positive_count = sum(matrix.y)
    negative_count = len(matrix.y) - positive_count
    scale_pos_weight = negative_count / positive_count if positive_count else 1.0

    model = lgbm_classifier(scale_pos_weight=scale_pos_weight)
    model.fit(matrix.x, matrix.y, feature_name=matrix.feature_names)

    ensure_parent(model_path)
    with model_path.open("wb") as handle:
        pickle.dump(model, handle)

    model_version = MORNING_AUCTION_VERSION
    save_training_metadata(
        metadata_path,
        model_version=model_version,
        feature_version=FEATURE_VERSION,
        feature_names=matrix.feature_names,
        train_date_range=_date_range(rows),
    )
    return {
        "model_version": model_version,
        "feature_names": matrix.feature_names,
        "positive_count": positive_count,
        "negative_count": negative_count,
    }


def _load_lgbm_classifier() -> object:
    try:
        from lightgbm import LGBMClassifier
    except (ImportError, OSError) as exc:
        raise RuntimeError(
            "LightGBM is installed but cannot load native runtime dependencies; install libomp "
            "or configure the training environment."
        ) from exc
    return LGBMClassifier


def save_training_metadata(
    path: Path,
    *,
    model_version: str,
    feature_version: str,
    feature_names: list[str],
    train_date_range: list[str],
) -> None:
    write_json(
        path,
        {
            "model_version": model_version,
            "feature_version": feature_version,
            "feature_names": feature_names,
            "train_date_range": train_date_range,
        },
    )


def _date_range(rows: Sequence[dict[str, object]]) -> list[str]:
    dates = sorted(str(row["trade_date"]) for row in rows if row.get("trade_date"))
    if not dates:
        return []
    return [dates[0], dates[-1]]


def _features(row: dict[str, object]) -> dict[str, object]:
    features = row.get("features")
    if isinstance(features, dict):
        return features
    return {}


def _feature_value(value: object) -> float:
    if value is None:
        return 0.0
    return float(value)
