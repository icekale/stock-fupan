from __future__ import annotations

import argparse
import json
import re
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


UPSTREAM_REPO = "https://github.com/simonlin1212/a-stock-data"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Refresh the vendored a-stock-data SKILL.md reference."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).resolve().parents[3] / "docs" / "vendor" / "a-stock-data",
    )
    args = parser.parse_args()

    skill_text, commit = fetch_upstream_skill()
    metadata = update_vendor(
        output_dir=args.output_dir,
        skill_text=skill_text,
        commit=commit,
        updated_at=datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds"),
    )
    print(json.dumps(metadata, ensure_ascii=False, indent=2))


def fetch_upstream_skill() -> tuple[str, str]:
    with tempfile.TemporaryDirectory() as tmp:
        checkout = Path(tmp) / "a-stock-data"
        subprocess.run(
            ["git", "clone", "--depth", "1", UPSTREAM_REPO, str(checkout)],
            check=True,
            stdout=subprocess.DEVNULL,
        )
        commit = subprocess.check_output(
            ["git", "-C", str(checkout), "rev-parse", "HEAD"],
            text=True,
        ).strip()
        return (checkout / "SKILL.md").read_text(encoding="utf-8"), commit


def update_vendor(
    output_dir: Path,
    skill_text: str,
    commit: str,
    updated_at: str,
) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "SKILL.md").write_text(skill_text, encoding="utf-8")
    metadata = {
        "upstream_repo": UPSTREAM_REPO,
        "upstream_commit": commit,
        "version": _extract_version(skill_text),
        "updated_at": updated_at,
        "local_note": "Reference copy only; runtime provider maps the needed endpoints explicitly.",
    }
    (output_dir / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return metadata


def _extract_version(skill_text: str) -> str:
    match = re.search(r"^version:\s*(.+)$", skill_text, flags=re.MULTILINE)
    return match.group(1).strip() if match else "unknown"


if __name__ == "__main__":
    main()
