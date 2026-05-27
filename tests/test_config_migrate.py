"""Tests for config.toml merge migration."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from app.config.migrate import merge_config_defaults


@pytest.fixture
def example_toml(tmp_path: Path) -> Path:
    p = tmp_path / "config.toml.example"
    p.write_text(
        """
[recording]
chunk_duration_seconds = 300

[update]
enabled = true
github_repo = "test/bgrec"
""",
        encoding="utf-8",
    )
    return p


def test_merge_adds_missing_keys(example_toml: Path, tmp_path: Path) -> None:
    user = tmp_path / "config.toml"
    user.write_text("[recording]\nchunk_duration_seconds = 600\n", encoding="utf-8")
    result = merge_config_defaults(user, example_toml)
    assert result.changed
    assert any("update" in k for k in result.keys_added)
    text = user.read_text(encoding="utf-8")
    assert "[update]" in text
    assert "github_repo" in text
    assert "chunk_duration_seconds = 600" in text


def test_merge_preserves_user_values(example_toml: Path, tmp_path: Path) -> None:
    user = tmp_path / "config.toml"
    user.write_text(
        "[recording]\nchunk_duration_seconds = 120\n[update]\nenabled = false\n",
        encoding="utf-8",
    )
    result = merge_config_defaults(user, example_toml)
    assert "chunk_duration_seconds" not in " ".join(result.keys_added)
    text = user.read_text(encoding="utf-8")
    assert "chunk_duration_seconds = 120" in text
    assert "enabled = false" in text


def test_dry_run_no_write(example_toml: Path, tmp_path: Path) -> None:
    user = tmp_path / "config.toml"
    user.write_text("[recording]\nchunk_duration_seconds = 300\n", encoding="utf-8")
    before = user.read_text(encoding="utf-8")
    result = merge_config_defaults(user, example_toml, dry_run=True)
    assert result.changed
    assert user.read_text(encoding="utf-8") == before
