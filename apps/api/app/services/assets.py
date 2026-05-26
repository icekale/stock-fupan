import json
import re
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any


_VERSION_RE = re.compile(r"^v(\d+)$")


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


def _validate_path_component(name: str, value: str) -> None:
    if not value or value in {".", ".."} or "/" in value or "\\" in value:
        raise ValueError(f"{name} must be a single path component")


def _ensure_under_root(reports_root: Path, path: Path) -> None:
    root = reports_root.resolve(strict=False)
    candidate = path.resolve(strict=False)
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError("asset path must stay under reports_root") from exc


def _existing_version_numbers(report_type_dir: Path) -> list[int]:
    return [
        int(match.group(1))
        for path in report_type_dir.iterdir()
        if path.is_dir() and (match := _VERSION_RE.fullmatch(path.name))
    ]


def create_report_asset_dir(reports_root: Path, trade_date: str, kind: str) -> AssetPaths:
    _validate_path_component("trade_date", trade_date)
    _validate_path_component("kind", kind)

    report_type_dir = reports_root / trade_date / kind
    _ensure_under_root(reports_root, report_type_dir)
    report_type_dir.mkdir(parents=True, exist_ok=True)

    next_number = max(_existing_version_numbers(report_type_dir), default=0) + 1
    while True:
        version = f"v{next_number:03d}"
        root = report_type_dir / version
        _ensure_under_root(reports_root, root)
        try:
            root.mkdir()
        except FileExistsError:
            next_number += 1
            continue

        _ensure_under_root(reports_root, root)
        return AssetPaths(root=root, version=version)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    with NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as temp_file:
        temp_file.write(content)
        temp_path = Path(temp_file.name)

    try:
        temp_path.replace(path)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise
