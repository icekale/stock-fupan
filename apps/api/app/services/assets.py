import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class AssetPaths:
    root: Path
    version: str

    @property
    def snapshot(self) -> Path:
        return self.root / "snapshot.json"

    @property
    def facts(self) -> Path:
        return self.root / "facts.json"

    @property
    def news_raw(self) -> Path:
        return self.root / "news_raw.json"

    @property
    def llm_calls(self) -> Path:
        return self.root / "llm_calls.json"

    @property
    def report_dto(self) -> Path:
        return self.root / "report.dto.json"

    @property
    def report_html(self) -> Path:
        return self.root / "report.html"

    @property
    def report_png(self) -> Path:
        return self.root / "report.png"

    @property
    def notes(self) -> Path:
        return self.root / "notes.json"


def create_report_asset_dir(reports_root: Path, trade_date: str, kind: str) -> AssetPaths:
    report_type_dir = reports_root / trade_date / kind
    report_type_dir.mkdir(parents=True, exist_ok=True)

    existing_versions = [
        int(path.name[1:])
        for path in report_type_dir.glob("v[0-9][0-9][0-9]")
        if path.is_dir() and path.name[1:].isdigit()
    ]
    next_number = max(existing_versions, default=0) + 1
    version = f"v{next_number:03d}"
    root = report_type_dir / version
    root.mkdir(parents=True, exist_ok=False)

    return AssetPaths(root=root, version=version)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
