from __future__ import annotations

import pickle
from pathlib import Path
from typing import Sequence

from app.services.morning_auction.artifacts import read_json
from app.services.morning_auction.trainer import build_feature_matrix


def score_rows_with_model(
    rows: Sequence[dict[str, object]],
    *,
    model_path: Path,
    metadata_path: Path,
) -> list[dict[str, object]]:
    metadata = read_json(metadata_path)
    feature_names = [str(name) for name in metadata.get("feature_names", [])]
    with model_path.open("rb") as handle:
        model = pickle.load(handle)

    import pandas as pd

    x = pd.DataFrame(build_feature_matrix(rows, feature_names), columns=feature_names)
    probabilities = model.predict_proba(x)
    scored: list[dict[str, object]] = []
    for row, probability in zip(rows, probabilities, strict=True):
        scored.append({**row, "prob_3pct": float(probability[1])})
    return scored
