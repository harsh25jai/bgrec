"""Merge new default config keys from config.toml.example without overwriting user values."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib  # type: ignore[no-redef]

from app.config.settings import CONFIG_SCHEMA_VERSION, config_from_dict, default_config_path, save_config
from app.version import get_version

CONFIG_META_FILE = "config_meta.json"


@dataclass
class MergeResult:
    changed: bool = False
    keys_added: list[str] = field(default_factory=list)
    recommended_applied: list[str] = field(default_factory=list)
    backup_path: Path | None = None
    config_path: Path | None = None


def get_config_schema_version() -> int:
    bundled = _bundled_schema_version_file()
    if bundled and bundled.exists():
        try:
            return int(bundled.read_text(encoding="utf-8").strip())
        except ValueError:
            pass
    return CONFIG_SCHEMA_VERSION


def _bundled_schema_version_file() -> Path | None:
    candidates = [
        _resource_root() / "config" / "schema-version.txt",
        Path(__file__).resolve().parents[2] / "config" / "schema-version.txt",
    ]
    for path in candidates:
        if path.exists():
            return path
    return None


def resolve_config_example_path(explicit: Path | None = None) -> Path:
    if explicit and explicit.exists():
        return explicit
    candidates = [
        _resource_root() / "config" / "config.toml.example",
        Path(__file__).resolve().parents[2] / "config" / "config.toml.example",
    ]
    for path in candidates:
        if path.exists():
            return path
    raise FileNotFoundError(
        "config.toml.example not found. Pass --example-path or run from a full install/ZIP."
    )


def _resource_root() -> Path:
    import sys

    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parents[2]


def _load_toml_dict(path: Path) -> dict[str, Any]:
    return tomllib.loads(path.read_text(encoding="utf-8"))


def _deep_merge_missing(defaults: Any, user: Any, prefix: str = "") -> tuple[Any, list[str]]:
    added: list[str] = []
    if isinstance(defaults, dict):
        out = dict(user) if isinstance(user, dict) else {}
        for key, default_val in defaults.items():
            key_path = f"{prefix}.{key}" if prefix else key
            if key not in out:
                out[key] = default_val
                added.append(key_path)
            elif isinstance(default_val, dict):
                merged, sub = _deep_merge_missing(default_val, out.get(key), key_path)
                out[key] = merged
                added.extend(sub)
        return out, added
    return user if user is not None else defaults, added


def _apply_recommended(user: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Opt-in flips documented in TODO-OTA (only when user explicitly requests)."""
    applied: list[str] = []
    retention = user.setdefault("retention", {})
    if retention.get("delete_after_upload") is False:
        retention["delete_after_upload"] = True
        applied.append("retention.delete_after_upload")
    return user, applied


def load_config_meta(root: Path) -> dict[str, Any]:
    path = root / CONFIG_META_FILE
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def save_config_meta(root: Path, meta: dict[str, Any]) -> None:
    path = root / CONFIG_META_FILE
    path.write_text(json.dumps(meta, indent=2), encoding="utf-8")


def merge_config_defaults(
    user_path: Path | None = None,
    example_path: Path | None = None,
    *,
    dry_run: bool = False,
    apply_recommended: bool = False,
    merged_from_version: str | None = None,
) -> MergeResult:
    user_path = user_path or default_config_path()
    example = resolve_config_example_path(example_path)
    result = MergeResult(config_path=user_path)

    if not user_path.exists():
        if dry_run:
            result.keys_added.append("(entire file from example)")
            result.changed = True
            return result
        user_path.parent.mkdir(parents=True, exist_ok=True)
        user_path.write_text(example.read_text(encoding="utf-8"), encoding="utf-8")
        result.changed = True
        result.keys_added.append("(created from example)")
        _write_meta(user_path.parent, merged_from_version)
        return result

    user_data = _load_toml_dict(user_path)
    example_data = _load_toml_dict(example)
    merged, added = _deep_merge_missing(example_data, user_data)
    result.keys_added = added

    if apply_recommended:
        merged, rec = _apply_recommended(merged)
        result.recommended_applied = rec

    if not added and not result.recommended_applied:
        return result

    result.changed = True
    if dry_run:
        return result

    backup = user_path.with_name(f"config.toml.bak.{get_version()}")
    backup.write_text(user_path.read_text(encoding="utf-8"), encoding="utf-8")
    result.backup_path = backup

    cfg = config_from_dict(merged)
    save_config(cfg, user_path)
    _write_meta(user_path.parent, merged_from_version)
    return result


def _write_meta(root: Path, merged_from_version: str | None) -> None:
    meta = load_config_meta(root)
    meta["config_schema_version"] = get_config_schema_version()
    meta["last_merged_at"] = time.time()
    if merged_from_version:
        meta["merged_from_version"] = merged_from_version
    save_config_meta(root, meta)
