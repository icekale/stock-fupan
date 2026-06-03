#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.providers.thsdk import ThsdkProvider  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe THSDK capabilities for stock-fupan.")
    parser.add_argument("--skip-live", action="store_true", help="Only check import availability.")
    parser.add_argument("--keyword", default="今日涨停", help="问财查询关键词。")
    parser.add_argument("--symbol", default="300033", help="用于 K 线/分时探测的 6 位股票代码。")
    args = parser.parse_args()

    provider = ThsdkProvider.from_installed_package()
    result = provider.check_available() if args.skip_live else provider.probe(args.keyword, args.symbol)
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2, default=str))
    return _exit_code(result.status)


def _exit_code(status: Any) -> int:
    if status in {"success", "available"}:
        return 0
    if status == "unavailable":
        return 2
    return 1


if __name__ == "__main__":
    sys.exit(main())
