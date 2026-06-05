import importlib.util
from pathlib import Path


def _load_update_script():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "update_a_stock_data_vendor.py"
    spec = importlib.util.spec_from_file_location("update_a_stock_data_vendor", script_path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_update_a_stock_data_vendor_writes_skill_and_metadata(tmp_path) -> None:
    module = _load_update_script()

    metadata = module.update_vendor(
        output_dir=tmp_path,
        skill_text="---\nname: a-stock-data\nversion: 3.2.2\n---\n# A股全栈数据工具包\n",
        commit="abc123",
        updated_at="2026-06-05T19:00:00+08:00",
    )

    assert (tmp_path / "SKILL.md").read_text(encoding="utf-8").startswith("---\nname: a-stock-data")
    assert metadata["upstream_commit"] == "abc123"
    assert metadata["version"] == "3.2.2"
    assert metadata["upstream_repo"] == "https://github.com/simonlin1212/a-stock-data"
