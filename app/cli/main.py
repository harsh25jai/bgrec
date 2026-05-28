"""Command-line interface for bgrec."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from app.platform_check import require_windows

require_windows()

from app.runtime_bootstrap import (
    bootstrap_runtime,
    drive_discovery_status,
    ssl_certificate_status,
)

bootstrap_runtime()

from app.config.settings import (
    AppConfig,
    default_config_path,
    load_config,
    save_config,
)
from app.logging.setup import configure_logging, get_logger
from app.recorder.audio_recorder import list_input_devices
from app.scheduler.coordinator import ServiceCoordinator
from app.service.singleton import is_daemon_lock_held
from app.service.daemon import (
    StopResult,
    is_daemon_active,
    run_foreground,
    spawn_background,
    state_path,
    stop_daemon,
    wait_for_daemon_active,
    reconcile_daemon_state,
)
from app.service.startup_ops import prepare_fresh_service_start
from app.service.state import DaemonState
from app.startup.windows_startup import WindowsStartupManager
from app.uploader.drive_client import DriveClient
from app.config.migrate import get_config_schema_version, merge_config_defaults
from app.config.migrate import load_config_meta
from app.updater.apply import apply_update, is_ota_target_install, read_current_meta, rollback_exe
from app.updater.service import check_for_updates, ensure_update_repo, try_auto_apply
from app.health.report import assess_health, format_issues_for_status
from app.health.state_issues import (
    ISSUES_CLEARED_AFTER_GOOGLE_LOGIN,
    clear_persisted_health_issues,
)
from app.install.portable import (
    bin_exe_path,
    get_portable_bin_version,
    is_running_installed_binary,
    portable_install_exists,
    wrong_executable_hint,
)
from app.version import get_version

app = typer.Typer(
    name="bgrec",
    help="bgrec — user-consented microphone capture with encrypted Google Drive backup.",
    no_args_is_help=True,
)
console = Console()
log = get_logger("cli")


def _load() -> AppConfig:
    return load_config()


@app.command()
def start(
    background: bool = typer.Option(
        True,
        "--background/--foreground",
        help="Run detached in background (default). Use --foreground to stay in this terminal.",
    ),
    fresh: bool = typer.Option(
        True,
        "--fresh/--no-fresh",
        help="Stop any running daemon and clear stale logs before starting (default).",
    ),
) -> None:
    """Start background recording service (fresh restart + upload nudge by default)."""
    cfg = _load()
    paths = cfg.ensure_directories()

    if not background:
        configure_logging(paths["logs"], level=cfg.logging.level)

        def factory():
            return ServiceCoordinator(cfg)

        run_foreground(factory)
        return

    if fresh:
        stop_result, logs_removed = prepare_fresh_service_start(paths["logs"])
        if stop_result == StopResult.STOPPED:
            console.print("[dim]Stopped previous daemon[/dim]")
        if logs_removed:
            console.print(f"[dim]Cleared {logs_removed} stale log file(s)[/dim]")

    configure_logging(paths["logs"], level=cfg.logging.level)

    spawn_background()
    state = wait_for_daemon_active(timeout=25.0)
    if state:
        console.print(f"[green]Started background daemon (pid={state.pid})[/green]")
        _print_upload_start_hint(cfg, paths, state)
    elif is_daemon_lock_held():
        console.print(
            "[yellow]Daemon is still starting (PyInstaller may take 10–20s).[/yellow]\n"
            "Check: bgrec status"
        )
        spath = state_path()
        state = reconcile_daemon_state(DaemonState.load(spath), spath)
        _print_upload_start_hint(cfg, paths, state)
    else:
        console.print(
            "[red]Failed to start daemon.[/red] Check logs in "
            f"{paths['logs']} (daemon-spawn.log, app.log).\n"
            "[dim]PYI temp-dir warnings on spawn are usually harmless.[/dim]"
        )
        raise typer.Exit(1)


def _print_upload_start_hint(cfg: AppConfig, paths: dict, state: DaemonState | None) -> None:
    if not cfg.upload.enabled:
        return
    drive = DriveClient(
        paths["credentials"],
        credentials_file=cfg.google.credentials_file,
        token_file=cfg.google.token_file,
        app_folder_name=cfg.google.app_folder_name,
    )
    auth_key, auth_msg = drive.google_auth_status()
    pending = len(state.pending_uploads) if state else 0
    if auth_key == "authenticated":
        if pending:
            console.print(
                f"[dim]Upload worker running — {pending} pending file(s) queued "
                "(uploads start automatically)[/dim]"
            )
        else:
            console.print("[dim]Upload worker running — no pending files[/dim]")
    else:
        console.print(f"[yellow]Upload deferred:[/yellow] {auth_msg}")


@app.command()
def restart(
    background: bool = typer.Option(True, "--background/--foreground", help="Restart detached."),
) -> None:
    """Stop the daemon if running, then start it again (fresh logs + upload nudge)."""
    if background:
        start(background=True, fresh=True)
    else:
        start(background=False, fresh=True)


@app.command()
def stop() -> None:
    """Stop the background recording service."""
    result = stop_daemon()
    if result == StopResult.STOPPED:
        console.print("[green]Service stopped[/green]")
    elif result == StopResult.FAILED:
        state = DaemonState.load(state_path())
        console.print(
            f"[red]Could not stop process (pid={state.pid}).[/red] "
            "Try closing it in Task Manager or run as admin: "
            f"taskkill /PID {state.pid} /F"
        )
        raise typer.Exit(1)
    else:
        console.print("[yellow]Service was not running (stale state cleared if needed)[/yellow]")


@app.command()
def status() -> None:
    """Show service status."""
    cfg = _load()
    paths = cfg.ensure_directories()
    spath = paths["root"] / "state.json"
    state = reconcile_daemon_state(DaemonState.load(spath), spath)

    drive = DriveClient(
        paths["credentials"],
        credentials_file=cfg.google.credentials_file,
        token_file=cfg.google.token_file,
        app_folder_name=cfg.google.app_folder_name,
    )
    auth_key, auth_msg = drive.google_auth_status()
    active = is_daemon_active(state)
    health = assess_health(cfg, state, daemon_active=active, auth_key=auth_key, auth_msg=auth_msg)

    table = Table(title="bgrec")
    table.add_column("Field", style="cyan")
    table.add_column("Value")
    if health.working_properly:
        table.add_row("Working properly", "[green]yes[/green]")
    else:
        table.add_row("Working properly", "[red]no[/red]")
    issues_text = format_issues_for_status(health.issues)
    if health.issues:
        table.add_row("Issues", f"[red]{issues_text}[/red]")
    else:
        table.add_row("Issues", "[green]none[/green]")
    table.add_row("Running", "yes" if active else "no")
    table.add_row("PID", str(state.pid or "—"))
    if state.last_chunk_at:
        ago = int(time.time() - state.last_chunk_at)
        table.add_row("Last chunk", f"{ago}s ago")
    else:
        table.add_row("Last chunk", "never")
    table.add_row("Chunks recorded", str(state.chunks_recorded))
    table.add_row("Pending uploads", str(len(state.pending_uploads)))
    table.add_row("Config", str(default_config_path()))
    table.add_row("Recordings", str(paths["recordings"]))
    table.add_row("Upload queue (cache)", str(paths["pending_uploads"]))
    table.add_row("Encryption", "enabled" if cfg.encryption.enabled else "disabled")
    table.add_row("Upload", "enabled" if cfg.upload.enabled else "disabled")
    table.add_row(
        "Sleep inhibition",
        "on" if cfg.recording.prevent_sleep_during_recording else "off",
    )
    if auth_key == "authenticated":
        table.add_row("Google auth", f"[green]{auth_msg}[/green]")
    else:
        table.add_row("Google auth", f"[yellow]{auth_msg}[/yellow]")
    _startup = WindowsStartupManager()
    table.add_row(
        "Startup (Run / task)",
        f"Run/task registered: {_startup.is_enabled()}",
    )
    service_ver = get_portable_bin_version()
    if service_ver and not is_running_installed_binary():
        table.add_row("App version (service)", service_ver)
        table.add_row("CLI version (this exe)", get_version())
        hint = wrong_executable_hint()
        if hint:
            table.add_row("Note", f"[yellow]{hint}[/yellow]")
    else:
        table.add_row("App version", service_ver or get_version())
    table.add_row("OTA auto-apply", "on" if cfg.update.auto_apply else "off")
    if cfg.update.enabled and cfg.update.auto_apply:
        table.add_row("OTA check interval", f"{cfg.update.check_interval_hours}h (also on each daemon start)")
    elif cfg.update.enabled:
        table.add_row("OTA check interval", f"{cfg.update.check_interval_hours}h (apply manual: bgrec update --yes)")
    ota_meta = read_current_meta()
    if ota_meta.get("version"):
        table.add_row("Last OTA version", str(ota_meta.get("version")))
    table.add_row("Config schema", str(get_config_schema_version()))

    console.print(table)


@app.command()
def version(
    check_update: bool = typer.Option(
        False,
        "--check-update",
        help="Query GitHub for a newer release (same as bgrec update --check).",
    ),
    porcelain: bool = typer.Option(
        False,
        "--porcelain",
        help="Print only the version of this executable (for scripts).",
    ),
) -> None:
    """Show installed version and OTA status."""
    if porcelain:
        console.print(get_version())
        return

    cfg = _load()
    paths = cfg.ensure_directories()
    meta = load_config_meta(paths["root"])
    ota = read_current_meta()
    service_ver = get_portable_bin_version()

    table = Table(title="bgrec version")
    table.add_column("Field", style="cyan")
    table.add_column("Value")
    if service_ver and not is_running_installed_binary():
        table.add_row("Service binary", f"[green]{service_ver}[/green] ({bin_exe_path()})")
        table.add_row("This command", f"{get_version()} ({sys.executable})")
    else:
        table.add_row("Installed", get_version())
    table.add_row("Config schema", str(get_config_schema_version()))
    table.add_row("OTA capable", "yes" if is_ota_target_install() else "no (dev/git install)")
    if ota.get("version"):
        table.add_row("Last OTA apply", str(ota.get("version")))
    if meta.get("last_merged_at"):
        table.add_row("Config last merged", str(int(meta["last_merged_at"])))
    if not is_running_installed_binary() and service_ver:
        hint = wrong_executable_hint()
        if hint:
            table.add_row("Note", f"[yellow]{hint}[/yellow]")
    else:
        table.add_row("Executable", sys.executable)
    console.print(table)

    if check_update:
        console.print()
        _print_update_check(cfg)


@app.command()
def update(
    check: bool = typer.Option(False, "--check", help="Check for updates only."),
    check_only: bool = typer.Option(
        False,
        "--check-only",
        help="Exit 0 if up to date, 1 if update available, 2 on error.",
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Apply without confirmation."),
    unattended: bool = typer.Option(
        False,
        "--unattended",
        help="Automatic apply (used by OTA scheduler; no prompts).",
    ),
    rollback: bool = typer.Option(False, "--rollback", help="Restore previous bgrec.exe.bak."),
    force: bool = typer.Option(False, "--force", help="Apply even if daemon stop fails."),
) -> None:
    """Check for or apply over-the-air updates (portable install)."""
    cfg = ensure_update_repo(_load())

    if rollback:
        result = rollback_exe()
        if result.success:
            console.print(f"[green]{result.message}[/green]")
        else:
            console.print(f"[red]{result.message}[/red]")
            raise typer.Exit(1)
        return

    result = check_for_updates(cfg)
    do_apply = yes or unattended or (cfg.update.auto_apply and not check and not check_only)

    if check or check_only or not do_apply:
        _print_update_check(cfg, result)
        if check_only:
            if result.error:
                raise typer.Exit(2)
            raise typer.Exit(1 if result.update_available else 0)
        if check or not result.update_available:
            return
        if not yes and not unattended:
            console.print("[dim]Run: bgrec update --yes[/dim]")
            return

    if not result.manifest:
        raise typer.Exit(1)

    if not result.update_available:
        if not unattended:
            console.print(f"[green]{result.message}[/green]")
        raise typer.Exit(0)

    if not result.ota_capable:
        if not unattended:
            console.print(
                "[yellow]OTA apply requires portable install at %LOCALAPPDATA%\\bgrec\\bin\\bgrec.exe[/yellow]"
            )
        raise typer.Exit(1)

    if not yes and not unattended and not cfg.update.auto_apply:
        typer.confirm(f"Download and install {result.manifest.version}?", abort=True)

    if unattended:
        if try_auto_apply(cfg, result, unattended=True, force=force):
            raise typer.Exit(0)
        raise typer.Exit(1)

    console.print(f"[cyan]Applying update {result.manifest.version}…[/cyan]")
    applied = apply_update(result.manifest, force=force, restart=True)
    if applied.success:
        lines = applied.message.splitlines()
        console.print(f"[green]{lines[0]}[/green]")
        for line in lines[1:]:
            console.print(f"[yellow]{line}[/yellow]")
        if applied.backup_exe:
            console.print(f"[dim]Backup: {applied.backup_exe}[/dim]")
        verify = bin_exe_path() if portable_install_exists() else Path(sys.executable)
        console.print(f'[dim]Verify: "{verify}" version[/dim]')
    else:
        console.print(f"[red]{applied.message}[/red]")
        raise typer.Exit(1)


def _print_update_check(cfg: AppConfig | None = None, result=None) -> None:
    result = result or check_for_updates(cfg or _load())
    if result.error and not result.remote_version:
        console.print(f"[red]{result.message}[/red]")
        if "github_repo" in (result.message or ""):
            console.print(
                "[dim]Set in config.toml: [update] github_repo = \"owner/bgrec\"[/dim]"
            )
        return
    if result.update_available:
        console.print(f"[yellow]{result.message}[/yellow]")
        if result.manifest and result.manifest.notes:
            console.print(f"[dim]{result.manifest.notes}[/dim]")
    else:
        console.print(f"[green]{result.message}[/green]")
    if result.manifest_url:
        console.print(f"[dim]Manifest: {result.manifest_url}[/dim]")


@app.command("doctor")
def doctor() -> None:
    """Verify bundled runtime prerequisites (discovery docs, TLS). Used after build."""
    disc_ok, disc_msg = drive_discovery_status()
    if not disc_ok:
        console.print(f"[red]Drive discovery:[/red] {disc_msg}")
        raise typer.Exit(1)

    tls_ok, tls_msg = ssl_certificate_status()
    if not tls_ok:
        console.print(f"[red]TLS:[/red] {tls_msg}")
        raise typer.Exit(1)

    console.print("[green]OK[/green] Drive discovery and TLS certificate bundle")
    console.print(f"[dim]Discovery: {disc_msg}[/dim]")
    console.print(f"[dim]TLS: {tls_msg}[/dim]")


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
    if clear_persisted_health_issues(*ISSUES_CLEARED_AFTER_GOOGLE_LOGIN):
        console.print("[dim]Cleared stale health issues from daemon state[/dim]")
    if is_daemon_active():
        console.print(
            "[dim]Daemon is running — it will pick up auth within ~15s. "
            "To upload now: bgrec upload-pending[/dim]"
        )
    console.print("[green]Google Drive authenticated successfully[/green]")


@app.command("upload-pending")
def upload_pending() -> None:
    """Upload all pending encrypted recordings to Google Drive."""
    cfg = _load()
    coord = ServiceCoordinator(cfg)
    count = coord.upload_queue.process_pending(blocking=True)
    console.print(f"[green]Uploaded {count} file(s)[/green]")


config_app = typer.Typer(help="View or update configuration.")
app.add_typer(config_app, name="config")


@config_app.command("show")
def config_show() -> None:
    """Show current config.toml (same as `bgrec config`)."""
    console.print_json(json.dumps(_config_display(_load())))


@config_app.callback(invoke_without_command=True)
def config_cmd(
    ctx: typer.Context,
    show: bool = typer.Option(True, "--show/--edit", help="Show current config."),
    key: Optional[str] = typer.Option(None, help="Set key using dotted path, e.g. recording.sample_rate"),
    value: Optional[str] = typer.Option(None, help="New value for key."),
) -> None:
    """View or update configuration."""
    if ctx.invoked_subcommand is not None:
        return
    cfg = _load()
    if key and value is not None:
        _set_nested(cfg, key, _parse_value(value))
        path = save_config(cfg)
        # Only touch the Run key when startup settings change (not for unrelated keys like update.github_repo).
        if key == "startup.enabled" or key.startswith("startup."):
            WindowsStartupManager().sync(cfg.startup.enabled)
        console.print(f"[green]Updated {key} -> saved to {path}[/green]")
        return
    if show:
        console.print_json(json.dumps(_config_display(cfg)))


@config_app.command("migrate")
def config_migrate(
    dry_run: bool = typer.Option(False, "--dry-run", help="Show keys that would be added."),
    apply_recommended: bool = typer.Option(
        False,
        "--apply-recommended",
        help="Apply documented default flips (e.g. delete_after_upload).",
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation for --apply-recommended."),
) -> None:
    """Merge missing keys from config.toml.example into your config.toml."""
    if apply_recommended and not yes and not dry_run:
        typer.confirm("Apply recommended config changes?", abort=True)
    result = merge_config_defaults(dry_run=dry_run, apply_recommended=apply_recommended)
    if not result.changed:
        console.print("[green]Config is up to date (no missing keys).[/green]")
        return
    if dry_run:
        console.print("[yellow]Would add keys:[/yellow]")
        for k in result.keys_added:
            console.print(f"  + {k}")
        if apply_recommended:
            console.print("[yellow]Would apply recommended:[/yellow]", result.recommended_applied)
        return
    console.print(f"[green]Config updated: {result.config_path}[/green]")
    if result.backup_path:
        console.print(f"[dim]Backup: {result.backup_path}[/dim]")
    for k in result.keys_added:
        console.print(f"  + {k}")
    for k in result.recommended_applied:
        console.print(f"  ~ {k}")


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
    WindowsStartupManager().enable(
        use_task=cfg.startup.use_task_scheduler,
        use_registry=cfg.startup.use_registry,
        logon_delay_seconds=cfg.startup.logon_delay_seconds,
    )
    console.print("[green]Startup configured[/green] (Task Scheduler + Run key + StartupApproved)")
    for line in WindowsStartupManager().diagnostics():
        console.print(f"[dim]  {line}[/dim]")


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
