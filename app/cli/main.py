"""Command-line interface for Background Audio Recorder."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from app.platform_check import require_windows

require_windows()

from app.config.settings import (
    AppConfig,
    default_config_path,
    load_config,
    save_config,
)
from app.crypto.encryption import EncryptionManager
from app.logging.setup import configure_logging, get_logger
from app.recorder.audio_recorder import list_input_devices
from app.scheduler.coordinator import ServiceCoordinator
from app.service.daemon import is_process_running, run_foreground, spawn_background, state_path, stop_daemon
from app.service.state import DaemonState
from app.startup.windows_startup import WindowsStartupManager
from app.uploader.drive_client import DriveClient

app = typer.Typer(
    name="bgrec",
    help="Background Audio Recorder — user-consented microphone capture with encrypted Google Drive backup.",
    no_args_is_help=True,
)
console = Console()
log = get_logger("cli")


def _load() -> AppConfig:
    return load_config()


@app.command()
def start(
    background: bool = typer.Option(False, "--background", help="Run detached in background."),
    foreground: bool = typer.Option(False, "--foreground", help="Run in foreground (used by daemon)."),
) -> None:
    """Start background recording service."""
    cfg = _load()
    paths = cfg.ensure_directories()
    configure_logging(paths["logs"], level=cfg.logging.level)

    state = DaemonState.load(state_path())
    if state.running and state.pid and is_process_running(state.pid):
        console.print(f"[yellow]Already running (pid={state.pid})[/yellow]")
        raise typer.Exit(0)

    if background and not foreground:
        pid = spawn_background()
        console.print(f"[green]Started background process (pid={pid})[/green]")
        return

    def factory():
        return ServiceCoordinator(cfg)

    run_foreground(factory)


@app.command()
def stop() -> None:
    """Stop the background recording service."""
    if stop_daemon():
        console.print("[green]Service stopped[/green]")
    else:
        console.print("[yellow]Service was not running[/yellow]")


@app.command()
def status() -> None:
    """Show service status."""
    cfg = _load()
    paths = cfg.ensure_directories()
    state = DaemonState.load(paths["root"] / "state.json")

    drive = DriveClient(
        paths["credentials"],
        credentials_file=cfg.google.credentials_file,
        token_file=cfg.google.token_file,
        app_folder_name=cfg.google.app_folder_name,
    )
    auth_key, auth_msg = drive.google_auth_status()

    table = Table(title="Background Audio Recorder")
    table.add_column("Field", style="cyan")
    table.add_column("Value")

    alive = state.pid and is_process_running(state.pid) if state.pid else False
    table.add_row("Running", str(alive and state.running))
    table.add_row("PID", str(state.pid or "—"))
    table.add_row("Chunks recorded", str(state.chunks_recorded))
    table.add_row("Pending uploads", str(len(state.pending_uploads)))
    table.add_row("Config", str(default_config_path()))
    table.add_row("Recordings", str(paths["recordings"]))
    table.add_row("Upload queue (cache)", str(paths["pending_uploads"]))
    table.add_row("Encryption", "enabled" if cfg.encryption.enabled else "disabled")
    table.add_row("Upload", "enabled" if cfg.upload.enabled else "disabled")
    if auth_key == "authenticated":
        table.add_row("Google auth", f"[green]{auth_msg}[/green]")
    else:
        table.add_row("Google auth", f"[yellow]{auth_msg}[/yellow]")
    table.add_row("Startup registry", str(WindowsStartupManager().is_enabled()))

    console.print(table)


@app.command("login-google")
def login_google() -> None:
    """Run Google OAuth desktop flow and save token."""
    cfg = _load()
    paths = cfg.ensure_directories()
    configure_logging(paths["logs"], level=cfg.logging.level)
    drive = DriveClient(
        paths["credentials"],
        credentials_file=cfg.google.credentials_file,
        token_file=cfg.google.token_file,
        app_folder_name=cfg.google.app_folder_name,
    )
    if not drive.is_configured():
        console.print(
            f"[red]Missing credentials file:[/red] {paths['credentials'] / cfg.google.credentials_file}\n"
            "Download OAuth Desktop credentials from Google Cloud Console."
        )
        raise typer.Exit(1)
    drive.authenticate(interactive=True)
    drive.ensure_app_folder()
    console.print("[green]Google Drive authenticated successfully[/green]")


@app.command("upload-pending")
def upload_pending() -> None:
    """Upload all pending encrypted recordings to Google Drive."""
    cfg = _load()
    coord = ServiceCoordinator(cfg)
    count = coord.upload_queue.process_pending(blocking=True)
    console.print(f"[green]Uploaded {count} file(s)[/green]")


@app.command()
def config(
    show: bool = typer.Option(True, "--show/--edit", help="Show current config."),
    key: Optional[str] = typer.Option(None, help="Set key using dotted path, e.g. recording.sample_rate"),
    value: Optional[str] = typer.Option(None, help="New value for key."),
) -> None:
    """View or update configuration."""
    cfg = _load()
    if key and value is not None:
        _set_nested(cfg, key, _parse_value(value))
        path = save_config(cfg)
        if cfg.startup.enabled:
            WindowsStartupManager().enable()
        console.print(f"[green]Updated {key} -> saved to {path}[/green]")
        return
    if show:
        console.print_json(json.dumps(_config_display(cfg)))


@app.command("list-recordings")
def list_recordings(
    limit: int = typer.Option(20, help="Max files to list."),
) -> None:
    """List local recording files."""
    cfg = _load()
    paths = cfg.ensure_directories()
    table = Table(title="Local Recordings")
    table.add_column("Name")
    table.add_column("Size (KB)")
    table.add_column("Modified")
    table.add_column("Location")
    shown = 0
    sources = [paths["recordings"], paths["recordings"] / "encrypted"]
    all_files: list[tuple[Path, str]] = []
    for base in sources:
        if not base.exists():
            continue
        label = "encrypted" if base.name == "encrypted" else "plain"
        for f in base.iterdir():
            if f.is_file():
                all_files.append((f, label))
    for f, label in sorted(all_files, key=lambda x: x[0].stat().st_mtime, reverse=True)[:limit]:
        stat = f.stat()
        table.add_row(f.name, f"{stat.st_size / 1024:.1f}", str(stat.st_mtime), label)
        shown += 1
    if shown == 0:
        console.print("[dim]No local recording files yet.[/dim]")
    console.print(table)


@app.command("delete-local-cache")
def delete_local_cache(
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation."),
) -> None:
    """Delete pending upload cache (not recordings)."""
    if not yes:
        typer.confirm("Delete all cached/pending upload files?", abort=True)
    cfg = _load()
    from app.retention.cleanup import RetentionManager

    paths = cfg.ensure_directories()
    n = RetentionManager(cfg, paths).delete_local_cache()
    console.print(f"[green]Removed {n} cached file(s)[/green]")


@app.command("decrypt")
def decrypt(
    encrypted: Path = typer.Argument(..., help="Path to a .enc file (local or downloaded from Drive)."),
    output: Optional[Path] = typer.Option(
        None, "--output", "-o", help="Output audio path (default: strip .enc → e.g. rec_20250101.flac)"
    ),
) -> None:
    """Decrypt a recording using your local encryption.key (then play with any media player)."""
    cfg = _load()
    paths = cfg.ensure_directories()
    enc_path = encrypted.expanduser().resolve()
    if not enc_path.is_file():
        console.print(f"[red]File not found:[/red] {enc_path}")
        raise typer.Exit(1)
    if enc_path.suffix != ".enc":
        console.print("[yellow]Warning: file does not end with .enc[/yellow]")

    out_path = output or enc_path.with_suffix("")
    key_path = paths["root"] / "encryption.key"
    if not key_path.exists():
        console.print(
            f"[red]Missing encryption key:[/red] {key_path}\n"
            "You need the same PC/key that encrypted this file."
        )
        raise typer.Exit(1)

    mgr = EncryptionManager(key_path, enabled=True)
    mgr.decrypt_file(enc_path, out_path)
    console.print(f"[green]Decrypted to:[/green] {out_path}")
    console.print("Open that file in VLC, Windows Media Player, etc.")


@app.command("list-devices")
def list_devices() -> None:
    """List available microphone input devices."""
    for dev in list_input_devices():
        console.print(f"  [{dev['index']}] {dev['name']} ({dev['channels']} ch)")


@app.command("install-startup")
def install_startup() -> None:
    """Add application to Windows startup (HKCU Run — visible to user)."""
    cfg = _load()
    cfg.startup.enabled = True
    try:
        save_config(cfg)
    except Exception as exc:
        console.print(f"[red]Could not save config (startup not changed):[/red] {exc}")
        raise typer.Exit(1) from exc
    WindowsStartupManager().enable()
    console.print("[green]Startup entry added to HKCU Run registry[/green]")


@app.command("uninstall-startup")
def uninstall_startup() -> None:
    """Remove application from Windows startup."""
    cfg = _load()
    cfg.startup.enabled = False
    try:
        save_config(cfg)
    except Exception as exc:
        console.print(f"[red]Could not save config:[/red] {exc}")
        raise typer.Exit(1) from exc
    WindowsStartupManager().disable()
    console.print("[green]Startup entry removed[/green]")


def _parse_value(raw: str):
    if raw.lower() in ("true", "false"):
        return raw.lower() == "true"
    try:
        return int(raw)
    except ValueError:
        pass
    try:
        return float(raw)
    except ValueError:
        pass
    return raw


def _set_nested(cfg: AppConfig, dotted: str, value) -> None:
    parts = dotted.split(".")
    if len(parts) < 2:
        raise typer.BadParameter("Use dotted path, e.g. recording.chunk_duration_seconds")
    section_name, field = parts[0], parts[1]
    section = getattr(cfg, section_name, None)
    if section is None or not hasattr(section, field):
        raise typer.BadParameter(f"Unknown config key: {dotted}")
    setattr(section, field, value)


def _config_display(cfg: AppConfig) -> dict:
    from dataclasses import asdict

    return asdict(cfg)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
