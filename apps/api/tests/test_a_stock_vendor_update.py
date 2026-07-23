from pathlib import Path

import httpx

from app.services import a_stock_vendor
from app.services.a_stock_vendor import (
    AStockVendorUpdater,
    VendorRemoteSnapshot,
    fetch_remote_snapshot,
)


def test_vendor_status_reads_local_metadata(tmp_path: Path) -> None:
    vendor_dir = tmp_path / "vendor"
    vendor_dir.mkdir()
    (vendor_dir / "metadata.json").write_text(
        '{"upstream_commit":"abc123","version":"3.2.2","updated_at":"2026-06-05T09:30:00+08:00"}',
        encoding="utf-8",
    )

    status = AStockVendorUpdater(vendor_dir=vendor_dir).status()

    assert status["local"]["upstream_commit"] == "abc123"
    assert status["local"]["version"] == "3.2.2"
    assert status["remote"] is None
    assert status["update_available"] is False
    assert status["auto_check_enabled"] is False


def test_vendor_check_records_remote_without_updating_skill(tmp_path: Path) -> None:
    vendor_dir = tmp_path / "vendor"
    vendor_dir.mkdir()
    (vendor_dir / "metadata.json").write_text(
        '{"upstream_commit":"old","version":"3.2.2","updated_at":"2026-06-05T09:30:00+08:00"}',
        encoding="utf-8",
    )

    def fetcher() -> VendorRemoteSnapshot:
        return VendorRemoteSnapshot(
            skill_text="---\nversion: 3.3.0\n---\n# New\n",
            commit="new",
        )

    status = AStockVendorUpdater(vendor_dir=vendor_dir, fetcher=fetcher).check()

    assert status["local"]["upstream_commit"] == "old"
    assert status["remote"]["upstream_commit"] == "new"
    assert status["remote"]["version"] == "3.3.0"
    assert status["update_available"] is True
    assert not (vendor_dir / "SKILL.md").exists()


def test_vendor_status_does_not_report_update_when_fingerprint_matches_local_version(
    tmp_path: Path,
) -> None:
    vendor_dir = tmp_path / "vendor"
    vendor_dir.mkdir()
    (vendor_dir / "metadata.json").write_text(
        '{"upstream_commit":"abc123","version":"3.2.2","updated_at":"2026-06-05T09:30:00+08:00"}',
        encoding="utf-8",
    )
    (vendor_dir / "state.json").write_text(
        '{"remote":{"upstream_commit":"content:abc","version":"3.2.2"}}',
        encoding="utf-8",
    )

    status = AStockVendorUpdater(vendor_dir=vendor_dir).status()

    assert status["update_available"] is False


def test_vendor_update_writes_skill_and_metadata(tmp_path: Path) -> None:
    vendor_dir = tmp_path / "vendor"

    def fetcher() -> VendorRemoteSnapshot:
        return VendorRemoteSnapshot(
            skill_text="---\nversion: 3.3.0\n---\n# New\n",
            commit="new",
        )

    status = AStockVendorUpdater(vendor_dir=vendor_dir, fetcher=fetcher).update()

    assert (vendor_dir / "SKILL.md").read_text(encoding="utf-8").startswith("---\nversion: 3.3.0")
    assert status["local"]["upstream_commit"] == "new"
    assert status["local"]["version"] == "3.3.0"
    assert status["remote"]["upstream_commit"] == "new"
    assert status["update_available"] is False


def test_vendor_auto_check_setting_is_persisted(tmp_path: Path) -> None:
    updater = AStockVendorUpdater(vendor_dir=tmp_path / "vendor")

    status = updater.set_auto_check(True)

    assert status["auto_check_enabled"] is True
    assert AStockVendorUpdater(vendor_dir=tmp_path / "vendor").status()["auto_check_enabled"] is True


def test_vendor_auto_check_runs_only_when_due(tmp_path: Path) -> None:
    calls = 0

    def fetcher() -> VendorRemoteSnapshot:
        nonlocal calls
        calls += 1
        return VendorRemoteSnapshot(skill_text="---\nversion: 3.3.0\n---\n", commit="new")

    updater = AStockVendorUpdater(vendor_dir=tmp_path / "vendor", fetcher=fetcher)

    assert updater.run_auto_check_if_due() is None
    updater.set_auto_check(True)
    first = updater.run_auto_check_if_due(now_iso="2026-06-06T09:00:00+08:00")
    second = updater.run_auto_check_if_due(now_iso="2026-06-06T10:00:00+08:00")
    third = updater.run_auto_check_if_due(now_iso="2026-06-07T09:00:00+08:00")

    assert first is not None
    assert second is None
    assert third is not None
    assert calls == 2


def test_fetch_remote_snapshot_falls_back_to_content_fingerprint_when_commit_api_is_limited(monkeypatch) -> None:
    class FakeResponse:
        def __init__(self, text: str = "", json_payload: dict[str, object] | None = None, status_code: int = 200) -> None:
            self.text = text
            self._json_payload = json_payload or {}
            self.status_code = status_code
            self.request = httpx.Request("GET", "https://example.test")

        def raise_for_status(self) -> None:
            if self.status_code >= 400:
                raise httpx.HTTPStatusError("rate limited", request=self.request, response=httpx.Response(self.status_code))

        def json(self) -> dict[str, object]:
            return self._json_payload

    class FakeClient:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def __enter__(self) -> "FakeClient":
            return self

        def __exit__(self, *_args: object) -> None:
            pass

        def get(self, url: str) -> FakeResponse:
            if url == a_stock_vendor.RAW_SKILL_URL:
                return FakeResponse(text="---\nversion: 3.3.0\n---\n# skill\n")
            if url == a_stock_vendor.COMMITS_URL:
                return FakeResponse(status_code=403)
            raise AssertionError(url)

    monkeypatch.setattr(a_stock_vendor.httpx, "Client", FakeClient)

    snapshot = fetch_remote_snapshot()

    assert snapshot.skill_text.startswith("---\nversion: 3.3.0")
    assert snapshot.commit.startswith("content:")
