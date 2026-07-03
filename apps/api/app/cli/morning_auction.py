from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Sequence

from app.services.morning_auction.artifacts import ensure_parent, read_jsonl, write_jsonl
from app.services.morning_auction.backtest import backtest_top_n
from app.services.morning_auction.dataset import build_samples_for_trade_date, sample_to_row
from app.services.morning_auction.free_stockdb import FreeStockDbMorningAuctionDataSource
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

    dataset_parser = subparsers.add_parser("build-dataset")
    dataset_parser.add_argument("--source", choices=["free-stockdb"], required=True)
    dataset_parser.add_argument("--base-url", required=True)
    dataset_parser.add_argument("--start-date", type=_date_arg, required=True)
    dataset_parser.add_argument("--end-date", type=_date_arg, required=True)
    dataset_parser.add_argument("--lookback", type=_positive_int, default=120)
    dataset_parser.add_argument("--timeout-seconds", type=float, default=10.0)
    dataset_parser.add_argument("--output", required=True)

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

    if args.command == "build-dataset":
        if args.end_date < args.start_date:
            parser.error("end-date must be on or after start-date")
        source = FreeStockDbMorningAuctionDataSource(
            base_url=args.base_url,
            timeout_seconds=args.timeout_seconds,
        )
        rows = [
            sample_to_row(sample)
            for trade_date in _iter_dates(args.start_date, args.end_date)
            for sample in build_samples_for_trade_date(
                source,
                trade_date=trade_date.isoformat(),
                lookback=args.lookback,
            )
        ]
        output_path = Path(args.output)
        write_jsonl(output_path, rows)
        result = {
            "source": args.source,
            "start_date": args.start_date.isoformat(),
            "end_date": args.end_date.isoformat(),
            "rows": len(rows),
            "output": str(output_path),
        }
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


def _date_arg(value: str) -> date:
    text = value.strip()
    try:
        if len(text) == 8 and text.isdigit():
            return datetime.strptime(text, "%Y%m%d").date()
        return date.fromisoformat(text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("date must be YYYY-MM-DD or YYYYMMDD") from exc


def _iter_dates(start: date, end: date):
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


if __name__ == "__main__":
    raise SystemExit(main())
