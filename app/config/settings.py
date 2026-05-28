"""Application configuration loaded from TOML."""

from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib  # type: ignore[no-redef]

import tomli_w

CONFIG_SCHEMA_VERSION = 1


def _app_data_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or str(Path.home())
    data_dir = Path(base) / "bgrec"
    legacy = Path(base) / "BackgroundAudioRecorder"
    if not data_dir.exists() and legacy.exists():
        return legacy
    return data_dir


def default_config_path() -> Path:
    return _app_data_dir() / "config.toml"


def default_data_dirs() -> dict[str, Path]:
    root = _app_data_dir()
    return {
        "root": root,
        "recordings": root / "recordings",
        "cache": root / "cache",
        "logs": root / "logs",
        "pending_uploads": root / "cache" / "pending",
        "credentials": root / "credentials",
    }


@dataclass
class RecordingConfig:
    device: str | None = None  # None = default input
    chunk_duration_seconds: int = 300
    sample_rate: int = 16000
    channels: int = 1
    output_format: str = "mp3"  # flac | mp3
    mp3_bitrate: str = "64k"
    silence_detection: bool = False
    silence_threshold_db: float = -40.0
    silence_min_duration_seconds: float = 30.0
    prevent_sleep_during_recording: bool = True


@dataclass
class UploadConfig:
    enabled: bool = True
    retry_max_attempts: int = 5
    retry_delay_seconds: int = 30
    upload_workers: int = 1


@dataclass
class EncryptionConfig:
    enabled: bool = False


@dataclass
class RetentionConfig:
    local_retention_days: int = 7
    delete_after_upload: bool = True


@dataclass
class StartupConfig:
    enabled: bool = True
    use_registry: bool = True  # HKCU Run key (visible in Task Manager → Startup)
    use_task_scheduler: bool = True  # ONLOGON task (more reliable than Run alone)
    logon_delay_seconds: int = 30  # Wait after sign-in before starting (mic/desktop ready)


@dataclass
class LoggingConfig:
    level: str = "INFO"
    max_bytes: int = 5_242_880  # 5 MB
    backup_count: int = 5


@dataclass
class GoogleConfig:
    credentials_file: str = "credentials.json"
    token_file: str = "token.json"
    app_folder_name: str = "bgrec"


@dataclass
class UpdateConfig:
    enabled: bool = True
    github_repo: str = ""
    check_on_start: bool = True
    check_interval_hours: int = 6
    channel: str = "stable"  # stable | test
    manifest_url: str = ""
    auto_apply: bool = True


@dataclass
class AppConfig:
    recording: RecordingConfig = field(default_factory=RecordingConfig)
    upload: UploadConfig = field(default_factory=UploadConfig)
    encryption: EncryptionConfig = field(default_factory=EncryptionConfig)
    retention: RetentionConfig = field(default_factory=RetentionConfig)
    startup: StartupConfig = field(default_factory=StartupConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    google: GoogleConfig = field(default_factory=GoogleConfig)
    update: UpdateConfig = field(default_factory=UpdateConfig)
    paths: dict[str, str] = field(default_factory=dict)

    def resolve_paths(self) -> dict[str, Path]:
        defaults = default_data_dirs()
        resolved: dict[str, Path] = {}
        for key, default in defaults.items():
            override = self.paths.get(key)
            resolved[key] = Path(override) if override else default
        return resolved

    def ensure_directories(self) -> dict[str, Path]:
        paths = self.resolve_paths()
        for p in paths.values():
            p.mkdir(parents=True, exist_ok=True)
        paths["pending_uploads"].mkdir(parents=True, exist_ok=True)
        paths["encrypted_local"] = paths["recordings"] / "encrypted"
        paths["encrypted_local"].mkdir(parents=True, exist_ok=True)
        paths["upload_temp"] = paths["cache"] / "upload_temp"
        paths["upload_temp"].mkdir(parents=True, exist_ok=True)
        return paths


def _merge_dataclass(cls: type, data: dict[str, Any]) -> Any:
    valid = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
    filtered = {k: v for k, v in data.items() if k in valid}
    return cls(**filtered)


def config_from_dict(data: dict[str, Any]) -> AppConfig:
    return AppConfig(
        recording=_merge_dataclass(RecordingConfig, data.get("recording", {})),
        upload=_merge_dataclass(UploadConfig, data.get("upload", {})),
        encryption=_merge_dataclass(EncryptionConfig, data.get("encryption", {})),
        retention=_merge_dataclass(RetentionConfig, data.get("retention", {})),
        startup=_merge_dataclass(StartupConfig, data.get("startup", {})),
        logging=_merge_dataclass(LoggingConfig, data.get("logging", {})),
        google=_merge_dataclass(GoogleConfig, data.get("google", {})),
        update=_merge_dataclass(UpdateConfig, data.get("update", {})),
        paths=data.get("paths", {}),
    )


def config_to_dict(cfg: AppConfig) -> dict[str, Any]:
    from dataclasses import asdict

    return asdict(cfg)


def _strip_none_values(obj: Any) -> Any:
    """TOML 1.0 (tomllib) does not support null; omit optional fields instead."""
    if isinstance(obj, dict):
        out: dict[str, Any] = {}
        for key, value in obj.items():
            if value is None:
                continue
            cleaned = _strip_none_values(value)
            if cleaned == {} and not isinstance(value, (str, int, float, bool)):
                continue
            out[key] = cleaned
        return out
    if isinstance(obj, list):
        return [_strip_none_values(v) for v in obj if v is not None]
    return obj


def _repair_toml_null_syntax(text: str) -> str:
    """Remove invalid `= null` assignments (common mistake from JSON-style configs)."""
    lines: list[str] = []
    for line in text.splitlines():
        if re.match(r"^\s*\w+\s*=\s*null\s*($|#)", line, re.IGNORECASE):
            key = re.match(r"^\s*(\w+)\s*=", line)
            if key:
                lines.append(f"# {line.strip()}  # removed: TOML does not support null")
            continue
        lines.append(line)
    return "\n".join(lines) + ("\n" if text.endswith("\n") else "")


def _read_toml(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    try:
        return tomllib.loads(text)
    except tomllib.TOMLDecodeError as first_exc:
        repaired = _repair_toml_null_syntax(text)
        if repaired == text:
            raise RuntimeError(
                f"Invalid config file: {path}\n{first_exc}\n\n"
                "Fix or delete the file. Common issue: `device = null` is not valid TOML."
            ) from first_exc
        try:
            data = tomllib.loads(repaired)
        except tomllib.TOMLDecodeError as exc:
            raise RuntimeError(
                f"Invalid config file: {path}\n{exc}\n\n"
                "Fix or delete the file. A backup may exist as config.toml.bak."
            ) from exc
        backup = path.with_suffix(".toml.bak")
        backup.write_text(text, encoding="utf-8")
        path.write_text(repaired, encoding="utf-8")
        return data


def load_config(path: Path | None = None) -> AppConfig:
    config_path = path or default_config_path()
    if not config_path.exists():
        cfg = AppConfig()
        save_config(cfg, config_path)
        return cfg
    data = _read_toml(config_path)
    return config_from_dict(data)


def save_config(cfg: AppConfig, path: Path | None = None) -> Path:
    config_path = path or default_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    payload = _strip_none_values(config_to_dict(cfg))
    tmp_path = config_path.with_suffix(".toml.tmp")
    try:
        with tmp_path.open("wb") as f:
            tomli_w.dump(payload, f)
        tmp_path.replace(config_path)
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        raise
    return config_path
