"""Frozen-exe and Windows runtime setup (call before Google/HTTPS clients)."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


def _local_appdata_bgrec() -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or str(Path.home())
    return Path(base) / "bgrec"


def _persistent_ca_bundle() -> Path:
    return _local_appdata_bgrec() / "cacert.pem"


def _persistent_discovery_dir() -> Path:
    return _local_appdata_bgrec() / "discovery_cache" / "documents"


def _bundled_drive_v3_discovery() -> Path | None:
    """drive.v3.json inside the current process bundle (PyInstaller _MEIPASS or site-packages)."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        candidate = (
            Path(sys._MEIPASS)
            / "googleapiclient"
            / "discovery_cache"
            / "documents"
            / "drive.v3.json"
        )
        if candidate.is_file():
            return candidate

    try:
        import googleapiclient.discovery_cache as discovery_cache
    except ImportError:
        return None

    candidate = Path(discovery_cache.__file__).resolve().parent / "documents" / "drive.v3.json"
    return candidate if candidate.is_file() else None


def configure_ssl_certificates() -> str | None:
    """
    Point TLS clients at a valid CA bundle (fixes PyInstaller one-file + Google APIs).

    The background daemon can outlive the one-file parent's _MEI temp folder, so when
    frozen we copy certifi's bundle into %LOCALAPPDATA%\\bgrec\\cacert.pem.
    Returns the CA path used, or None if certifi is unavailable.
    """
    try:
        import certifi
    except ImportError:
        return None

    ca_path = Path(certifi.where())
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        for candidate in (
            Path(sys._MEIPASS) / "certifi" / "cacert.pem",
            Path(sys._MEIPASS) / "cacert.pem",
        ):
            if candidate.is_file():
                ca_path = candidate
                break

    if not ca_path.is_file():
        return None

    if getattr(sys, "frozen", False):
        dest = _persistent_ca_bundle()
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            if not dest.exists() or dest.stat().st_size != ca_path.stat().st_size:
                shutil.copy2(ca_path, dest)
            ca_path = dest
        except OSError:
            ca_path = ca_path

    ca = str(ca_path)
    os.environ["SSL_CERT_FILE"] = ca
    os.environ["REQUESTS_CA_BUNDLE"] = ca
    os.environ["CURL_CA_BUNDLE"] = ca
    return ca


def ssl_certificate_status() -> tuple[bool, str]:
    """Return (ok, detail) for status / health checks."""
    ca = configure_ssl_certificates()
    if not ca:
        return False, "TLS CA bundle unavailable (install certifi or rebuild bgrec.exe)"
    path = Path(ca)
    if not path.is_file():
        return False, f"TLS CA bundle missing: {ca}"
    return True, str(path)


def configure_drive_discovery_cache() -> Path | None:
    """
    Copy Drive v3 discovery JSON to %LOCALAPPDATA%\\bgrec (survives _MEI temp cleanup).

    The background daemon can outlive PyInstaller's extracted _MEIPASS folder when
    Windows cleans temp; static_discovery then fails until this persistent copy exists.
    """
    src = _bundled_drive_v3_discovery()
    if src is None:
        return None

    dest_dir = _persistent_discovery_dir()
    dest = dest_dir / "drive.v3.json"
    doc_dir = src.parent

    if getattr(sys, "frozen", False):
        try:
            dest_dir.mkdir(parents=True, exist_ok=True)
            if not dest.exists() or dest.stat().st_size != src.stat().st_size:
                shutil.copy2(src, dest)
            if dest.is_file():
                doc_dir = dest_dir
        except OSError:
            if dest.is_file():
                doc_dir = dest_dir
            elif not src.is_file():
                return None

    try:
        import googleapiclient.discovery_cache as discovery_cache

        discovery_cache.DISCOVERY_DOC_DIR = str(doc_dir)
    except ImportError:
        return None

    return doc_dir


def drive_discovery_status() -> tuple[bool, str]:
    """Return (ok, detail) for status / doctor."""
    configure_drive_discovery_cache()
    try:
        from googleapiclient.discovery_cache import get_static_doc
    except ImportError:
        return False, "google-api-python-client not installed"

    doc = get_static_doc("drive", "v3")
    if not doc:
        persistent = _persistent_discovery_dir() / "drive.v3.json"
        return (
            False,
            "drive.v3 discovery missing "
            f"(expected bundled copy or {persistent})",
        )
    return True, str(_persistent_discovery_dir() / "drive.v3.json")


def bootstrap_runtime() -> None:
    configure_ssl_certificates()
    configure_drive_discovery_cache()
