"""Persistent daemon state (PID, recording status, pending queue metadata)."""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from app.utils.file_lock import file_lock


@dataclass
class PendingUpload:
    local_path: str
    remote_name: str
    attempts: int = 0
    last_error: str | None = None
    created_at: float = field(default_factory=time.time)


@dataclass
class HealthIssue:
    code: str
    message: str
    since: float = field(default_factory=time.time)


@dataclass
class DaemonState:
    pid: int | None = None
    running: bool = False
    daemon_executable: str | None = None
    started_at: float | None = None
    last_chunk_at: float | None = None
    last_heartbeat_at: float | None = None
    chunks_recorded: int = 0
    pending_uploads: list[PendingUpload] = field(default_factory=list)
    issues: list[HealthIssue] = field(default_factory=list)

    @classmethod
    def load(cls, path: Path) -> DaemonState:
        if not path.exists():
            return cls()
        with file_lock(path):
            data = json.loads(path.read_text(encoding="utf-8"))
        pending = [PendingUpload(**p) for p in data.pop("pending_uploads", [])]
        raw_issues = data.pop("issues", [])
        issues = [HealthIssue(**i) for i in raw_issues]
        return cls(
            pending_uploads=pending,
            issues=issues,
            **{k: v for k, v in data.items() if k not in ("pending_uploads", "issues")},
        )

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload: dict[str, Any] = asdict(self)
        payload["pending_uploads"] = [asdict(p) for p in self.pending_uploads]
        payload["issues"] = [asdict(i) for i in self.issues]
        with file_lock(path):
            path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def set_issue(self, code: str, message: str) -> bool:
        """Record or update a health issue; returns True if state changed."""
        text = message.strip()[:500]
        for item in self.issues:
            if item.code == code:
                if item.message == text:
                    return False
                item.message = text
                item.since = time.time()
                return True
        self.issues.append(HealthIssue(code=code, message=text))
        return True

    def clear_issue(self, code: str) -> bool:
        before = len(self.issues)
        self.issues = [i for i in self.issues if i.code != code]
        return len(self.issues) != before

    def add_pending(self, local_path: Path, remote_name: str) -> None:
        self.pending_uploads.append(
            PendingUpload(local_path=str(local_path), remote_name=remote_name)
        )

    def remove_pending(self, local_path: Path) -> None:
        key = str(local_path)
        self.pending_uploads = [p for p in self.pending_uploads if p.local_path != key]
