import json
from pathlib import Path

from app.services.assets import AssetPaths, create_report_asset_dir, write_json


def test_create_report_asset_dir_uses_next_version(tmp_path: Path) -> None:
    first = create_report_asset_dir(tmp_path, "2026-05-26", "close")
    second = create_report_asset_dir(tmp_path, "2026-05-26", "close")

    assert first.version == "v001"
    assert second.version == "v002"
    assert first.root == tmp_path / "2026-05-26" / "close" / "v001"
    assert second.root == tmp_path / "2026-05-26" / "close" / "v002"
    assert first.root.exists()
    assert second.root.exists()


def test_write_json_outputs_pretty_utf8(tmp_path: Path) -> None:
    paths = AssetPaths(root=tmp_path, version="v001")
    write_json(paths.snapshot, {"name": "机器人", "score": 86.5})

    loaded = json.loads(paths.snapshot.read_text(encoding="utf-8"))

    assert loaded == {"name": "机器人", "score": 86.5}
    assert "机器人" in paths.snapshot.read_text(encoding="utf-8")
