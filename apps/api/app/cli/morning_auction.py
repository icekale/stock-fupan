from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from app.services.morning_auction.artifacts import ensure_parent, read_jsonl
from app.services.morning_auction.backtest import backtest_top_n
from app.services.morning_auction.trainer import train_lightgbm_model


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Morning auction model tools.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    train_parser = subparsers.add_parser("train")
    train_parser.add_argument("--dataset", required=True)
    train_parser.add_argument("--model", required=True)
    train_parser.add_argument("--metadata", required=True)

    backtest_parser = subparsers.add_parser("backtest")
    backtest_parser.add_argument("--predictions", required=True)
    backtest_parser.add_argument("--top-n", type=_positive_int, default=3)
    backtest_parser.add_argument("--output")

    args = parser.parse_args(argv)
    if args.command == "train":
        dataset_path = Path(args.dataset)
        if not dataset_path.exists():
            parser.error(f"dataset file does not exist: {dataset_path}")
        result = train_lightgbm_model(
            read_jsonl(dataset_path),
            Path(args.model),
            Path(args.metadata),
        )
        _print_json(result)
        return 0

    predictions_path = Path(args.predictions)
    if not predictions_path.exists():
        parser.error(f"predictions file does not exist: {predictions_path}")
    result = backtest_top_n(read_jsonl(predictions_path), top_n=args.top_n)
    if args.output:
        output_path = Path(args.output)
        ensure_parent(output_path)
        output_path.write_text(_json(result), encoding="utf-8")
    _print_json(result)
    return 0


def _print_json(payload: dict[str, object]) -> None:
    print(_json(payload))


def _json(payload: dict[str, object]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("top-n must be positive")
    return parsed


if __name__ == "__main__":
    raise SystemExit(main())
