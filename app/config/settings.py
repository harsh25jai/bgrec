"""Application configuration loaded from TOML."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib  # type: ignore[no-redef]

import tomli_w


def _app_data_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or str(Path.home())
    return Path(base) / "BackgroundAudioRecorder"


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
    output_format: str = "flac"  # flac | mp3
    mp3_bitrate: str = "64k"
    silence_detection: bool = False
    silence_threshold_db: float = -40.0
    silence_min_duration_seconds: float = 30.0


@dataclass
class UploadConfig:
    enabled: bool = True
    retry_max_attempts: int = 5
    retry_delay_seconds: int = 30
    upload_workers: int = 2


@dataclass
class EncryptionConfig:
    enabled: bool = True


@dataclass
class RetentionConfig:
    local_retention_days: int = 7
    delete_after_upload: bool = False


@dataclass
class StartupConfig:
    enabled: bool = False
    use_registry: bool = True  # HKCU Run key; alternative is scheduled task


@dataclass
class LoggingConfig:
    level: str = "INFO"
    max_bytes: int = 5_242_880  # 5 MB
    backup_count: int = 5


@dataclass
class GoogleConfig:
    credentials_file: str = "credentials.json"
    token_file: str = "token.json"
    app_folder_name: str = "BackgroundAudioRecorder"


@dataclass
class AppConfig:
    recording: RecordingConfig = field(default_factory=RecordingConfig)
    upload: UploadConfig = field(default_factory=UploadConfig)
    encryption: EncryptionConfig = field(default_factory=EncryptionConfig)
    retention: RetentionConfig = field(default_factory=RetentionConfig)
    startup: StartupConfig = field(default_factory=StartupConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    google: GoogleConfig = field(default_factory=GoogleConfig)
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
        (paths["pending_uploads"]).mkdir(parents=True, exist_ok=True)
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
        paths=data.get("paths", {}),
    )


def config_to_dict(cfg: AppConfig) -> dict[str, Any]:
    from dataclasses import asdict

    return asdict(cfg)


def load_config(path: Path | None = None) -> AppConfig:
    config_path = path or default_config_path()
    if not config_path.exists():
        cfg = AppConfig()
        save_config(cfg, config_path)
        return cfg
    with config_path.open("rb") as f:
        data = tomllib.load(f)
    return config_from_dict(data)


def save_config(cfg: AppConfig, path: Path | None = None) -> Path:
    config_path = path or default_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with config_path.open("wb") as f:
        tomli_w.dump(config_to_dict(cfg), f)
    return config_path
