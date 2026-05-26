import json
from errno import EEXIST
from pathlib import Path

import pytest

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


@pytest.mark.parametrize("trade_date", ["", "..", "2026/05/26", r"2026\05\26"])
def test_create_report_asset_dir_rejects_invalid_trade_date(
    tmp_path: Path, trade_date: str
) -> None:
    with pytest.raises(ValueError, match="trade_date"):
        create_report_asset_dir(tmp_path, trade_date, "close")


@pytest.mark.parametrize("kind", ["", "..", "close/extra", r"close\extra"])
def test_create_report_asset_dir_rejects_invalid_kind(tmp_path: Path, kind: str) -> None:
    with pytest.raises(ValueError, match="kind"):
        create_report_asset_dir(tmp_path, "2026-05-26", kind)


def test_create_report_asset_dir_handles_version_gaps_and_high_versions(
    tmp_path: Path,
) -> None:
    report_type_dir = tmp_path / "2026-05-26" / "close"
    (report_type_dir / "v001").mkdir(parents=True)
    (report_type_dir / "v010").mkdir()
    (report_type_dir / "v1000").mkdir()

    paths = create_report_asset_dir(tmp_path, "2026-05-26", "close")

    assert paths.version == "v1001"
    assert paths.root == report_type_dir / "v1001"
    assert paths.root.exists()


def test_create_report_asset_dir_retries_after_version_collision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original_mkdir = Path.mkdir
    collided = False

    def mkdir_with_collision(
        path: Path,
        mode: int = 0o777,
        parents: bool = False,
        exist_ok: bool = False,
    ) -> None:
        nonlocal collided
        if path.name == "v001" and not collided:
            collided = True
            raise FileExistsError(EEXIST, "File exists", str(path))
        return original_mkdir(path, mode=mode, parents=parents, exist_ok=exist_ok)

    monkeypatch.setattr(Path, "mkdir", mkdir_with_collision)

    paths = create_report_asset_dir(tmp_path, "2026-05-26", "close")

    assert collided
    assert paths.version == "v002"
    assert paths.root == tmp_path / "2026-05-26" / "close" / "v002"
    assert paths.root.exists()


def test_write_json_replaces_existing_file(tmp_path: Path) -> None:
    target = tmp_path / "snapshot.json"
    target.write_text('{"name": "旧"}\n', encoding="utf-8")

    write_json(target, {"name": "新"})

    assert json.loads(target.read_text(encoding="utf-8")) == {"name": "新"}


def test_write_json_keeps_existing_file_when_replace_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "snapshot.json"
    original_content = '{"name": "旧"}\n'
    target.write_text(original_content, encoding="utf-8")

    original_replace = Path.replace

    def replace_with_failure(path: Path, target_path: Path) -> Path:
        if target_path == target:
            raise OSError("replace failed")
        return original_replace(path, target_path)

    monkeypatch.setattr(Path, "replace", replace_with_failure)

    with pytest.raises(OSError, match="replace failed"):
        write_json(target, {"name": "新"})

    assert target.read_text(encoding="utf-8") == original_content


def test_write_json_outputs_pretty_utf8(tmp_path: Path) -> None:
    paths = AssetPaths(root=tmp_path, version="v001")
    write_json(paths.snapshot, {"name": "机器人", "score": 86.5})

    loaded = json.loads(paths.snapshot.read_text(encoding="utf-8"))

    assert loaded == {"name": "机器人", "score": 86.5}
    assert "机器人" in paths.snapshot.read_text(encoding="utf-8")
