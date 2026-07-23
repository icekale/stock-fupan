from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx


UPSTREAM_REPO = "https://github.com/simonlin1212/a-stock-data"
UPSTREAM_BRANCH = "main"
RAW_SKILL_URL = (
    "https://raw.githubusercontent.com/simonlin1212/a-stock-data/main/SKILL.md"
)
COMMITS_URL = "https://api.github.com/repos/simonlin1212/a-stock-data/commits/main"


@dataclass(frozen=True)
class VendorRemoteSnapshot:
    skill_text: str
    commit: str


class AStockVendorUpdater:
    def __init__(
        self,
        vendor_dir: Path,
        fetcher=None,
        timeout_seconds: float = 15,
    ) -> None:
        self.vendor_dir = vendor_dir
        self.fetcher = fetcher or (lambda: fetch_remote_snapshot(timeout_seconds=timeout_seconds))

    def status(self) -> dict[str, object]:
        state = self._read_state()
        return self._payload(
            local=self._read_local_metadata(),
            remote=state.get("remote"),
            auto_check_enabled=bool(state.get("auto_check_enabled", False)),
            last_checked_at=state.get("last_checked_at"),
            last_error=state.get("last_error"),
        )

    def check(self) -> dict[str, object]:
        return self._check(checked_at=_now_iso())

    def _check(self, checked_at: str) -> dict[str, object]:
        try:
            remote = self._remote_metadata(self.fetcher())
            state = self._read_state()
            state.update(
                {
                    "remote": remote,
                    "last_checked_at": checked_at,
                    "last_error": None,
                }
            )
            self._write_state(state)
        except Exception as exc:
            state = self._read_state()
            state.update({"last_checked_at": checked_at, "last_error": str(exc) or exc.__class__.__name__})
            self._write_state(state)
        return self.status()

    def update(self) -> dict[str, object]:
        snapshot = self.fetcher()
        remote = self._remote_metadata(snapshot)
        self.vendor_dir.mkdir(parents=True, exist_ok=True)
        (self.vendor_dir / "SKILL.md").write_text(snapshot.skill_text, encoding="utf-8")
        metadata = {
            "upstream_repo": UPSTREAM_REPO,
            "upstream_commit": snapshot.commit,
            "version": remote["version"],
            "updated_at": _now_iso(),
            "local_note": "Reference copy only; runtime provider maps the needed endpoints explicitly.",
        }
        (self.vendor_dir / "metadata.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        state = self._read_state()
        state.update(
            {
                "remote": remote,
                "last_checked_at": _now_iso(),
                "last_updated_at": metadata["updated_at"],
                "last_error": None,
            }
        )
        self._write_state(state)
        return self.status()

    def set_auto_check(self, enabled: bool) -> dict[str, object]:
        state = self._read_state()
        state["auto_check_enabled"] = enabled
        self._write_state(state)
        return self.status()

    def run_auto_check_if_due(self, now_iso: str | None = None) -> dict[str, object] | None:
        state = self._read_state()
        if not state.get("auto_check_enabled", False):
            return None
        now = _parse_iso(now_iso) if now_iso else datetime.now(ZoneInfo("Asia/Shanghai"))
        last_checked_at = state.get("last_checked_at")
        if isinstance(last_checked_at, str):
            last_checked = _parse_iso(last_checked_at)
            if last_checked is not None and now - last_checked < timedelta(hours=24):
                return None
        return self._check(checked_at=now.isoformat(timespec="seconds"))

    def _remote_metadata(self, snapshot: VendorRemoteSnapshot) -> dict[str, str]:
        return {
            "upstream_repo": UPSTREAM_REPO,
            "upstream_commit": snapshot.commit,
            "version": _extract_version(snapshot.skill_text),
        }

    def _read_local_metadata(self) -> dict[str, object] | None:
        path = self.vendor_dir / "metadata.json"
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    def _read_state(self) -> dict[str, object]:
        path = self.vendor_dir / "state.json"
        if not path.exists():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return payload if isinstance(payload, dict) else {}

    def _write_state(self, state: dict[str, object]) -> None:
        self.vendor_dir.mkdir(parents=True, exist_ok=True)
        (self.vendor_dir / "state.json").write_text(
            json.dumps(state, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def _payload(
        self,
        local: dict[str, object] | None,
        remote: object,
        auto_check_enabled: bool,
        last_checked_at: object,
        last_error: object,
    ) -> dict[str, object]:
        update_available = False
        if isinstance(remote, dict):
            remote_commit = remote.get("upstream_commit")
            local_commit = local.get("upstream_commit") if local else None
            remote_version = remote.get("version")
            local_version = local.get("version") if local else None
            if (
                isinstance(remote_commit, str)
                and remote_commit.startswith("content:")
                and remote_version == local_version
            ):
                update_available = False
            else:
                update_available = bool(remote_commit and remote_commit != local_commit)
        return {
            "local": local,
            "remote": remote if isinstance(remote, dict) else None,
            "update_available": update_available,
            "auto_check_enabled": auto_check_enabled,
            "last_checked_at": last_checked_at if isinstance(last_checked_at, str) else None,
            "last_error": last_error if isinstance(last_error, str) else None,
        }


def fetch_remote_snapshot(timeout_seconds: float = 15) -> VendorRemoteSnapshot:
    with httpx.Client(timeout=timeout_seconds, follow_redirects=True) as client:
        skill_response = client.get(RAW_SKILL_URL)
        skill_response.raise_for_status()
        skill_text = skill_response.text
        commit = _fetch_remote_commit(client) or _content_fingerprint(skill_text)
        return VendorRemoteSnapshot(skill_text=skill_text, commit=commit)


def _fetch_remote_commit(client: httpx.Client) -> str | None:
    try:
        commit_response = client.get(COMMITS_URL)
        commit_response.raise_for_status()
        commit_payload = commit_response.json()
    except (httpx.HTTPError, ValueError):
        return None
    commit = str(commit_payload.get("sha") or "").strip()
    return commit or None


def _content_fingerprint(text: str) -> str:
    return f"content:{hashlib.sha256(text.encode('utf-8')).hexdigest()}"


def _extract_version(skill_text: str) -> str:
    match = re.search(r"^version:\s*(.+)$", skill_text, flags=re.MULTILINE)
    return match.group(1).strip() if match else "unknown"


def _now_iso() -> str:
    return datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds")


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=ZoneInfo("Asia/Shanghai"))
    return parsed
