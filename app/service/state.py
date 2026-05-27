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
class DaemonState:
    pid: int | None = None
    running: bool = False
    started_at: float | None = None
    last_chunk_at: float | None = None
    chunks_recorded: int = 0
    pending_uploads: list[PendingUpload] = field(default_factory=list)

    @classmethod
    def load(cls, path: Path) -> DaemonState:
        if not path.exists():
            return cls()
        with file_lock(path):
            data = json.loads(path.read_text(encoding="utf-8"))
        pending = [PendingUpload(**p) for p in data.pop("pending_uploads", [])]
        return cls(pending_uploads=pending, **{k: v for k, v in data.items() if k != "pending_uploads"})

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload: dict[str, Any] = asdict(self)
        payload["pending_uploads"] = [asdict(p) for p in self.pending_uploads]
        with file_lock(path):
            path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def add_pending(self, local_path: Path, remote_name: str) -> None:
        self.pending_uploads.append(
            PendingUpload(local_path=str(local_path), remote_name=remote_name)
        )

    def remove_pending(self, local_path: Path) -> None:
        key = str(local_path)
        self.pending_uploads = [p for p in self.pending_uploads if p.local_path != key]
