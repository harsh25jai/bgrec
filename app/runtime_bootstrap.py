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


def _apply_ca_bundle(ca_path: Path) -> str | None:
    if not ca_path.is_file():
        return None
    ca = str(ca_path)
    os.environ["SSL_CERT_FILE"] = ca
    os.environ["REQUESTS_CA_BUNDLE"] = ca
    os.environ["CURL_CA_BUNDLE"] = ca
    return ca


def configure_ssl_certificates() -> str | None:
    """
    Point TLS clients at a valid CA bundle (fixes PyInstaller one-file + Google APIs).

    Prefer %LOCALAPPDATA%\\bgrec\\cacert.pem when present so long-running daemons keep
    working after Windows deletes _MEIPASS.
    """
    persistent = _persistent_ca_bundle()
    if persistent.is_file():
        return _apply_ca_bundle(persistent)

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
        try:
            persistent.parent.mkdir(parents=True, exist_ok=True)
            if not persistent.exists() or persistent.stat().st_size != ca_path.stat().st_size:
                shutil.copy2(ca_path, persistent)
            return _apply_ca_bundle(persistent)
        except OSError:
            pass

    return _apply_ca_bundle(ca_path)


def ssl_certificate_status() -> tuple[bool, str]:
    """Return (ok, detail) for status / health checks."""
    ca = configure_ssl_certificates()
    if not ca:
        return False, "TLS CA bundle unavailable (install certifi or rebuild bgrec.exe)"
    path = Path(ca)
    if not path.is_file():
        return False, f"TLS CA bundle missing: {ca}"
    return True, str(path)


def _set_discovery_doc_dir(doc_dir: Path) -> Path | None:
    try:
        import googleapiclient.discovery_cache as discovery_cache

        discovery_cache.DISCOVERY_DOC_DIR = str(doc_dir)
    except ImportError:
        return None
    return doc_dir


def configure_drive_discovery_cache() -> Path | None:
    """
    Use/copy Drive v3 discovery JSON under %LOCALAPPDATA%\\bgrec (survives _MEI cleanup).

    Persistent copy is checked first so daemons keep working after %TEMP% cleanup.
    """
    persistent_dir = _persistent_discovery_dir()
    persistent_doc = persistent_dir / "drive.v3.json"
    if persistent_doc.is_file():
        return _set_discovery_doc_dir(persistent_dir)

    src = _bundled_drive_v3_discovery()
    if src is None:
        return None

    if getattr(sys, "frozen", False):
        try:
            persistent_dir.mkdir(parents=True, exist_ok=True)
            if not persistent_doc.exists() or persistent_doc.stat().st_size != src.stat().st_size:
                shutil.copy2(src, persistent_doc)
            if persistent_doc.is_file():
                return _set_discovery_doc_dir(persistent_dir)
        except OSError:
            if persistent_doc.is_file():
                return _set_discovery_doc_dir(persistent_dir)
            return None

    return _set_discovery_doc_dir(src.parent)


def drive_discovery_status() -> tuple[bool, str]:
    """Return (ok, detail) for status / doctor."""
    configure_drive_discovery_cache()
    try:
        from googleapiclient.discovery_cache import get_static_doc
    except ImportError:
        return False, "google-api-python-client not installed"

    doc = get_static_doc("drive", "v3")
    if not doc:
        return (
            False,
            "drive.v3 discovery missing "
            f"(expected {persistent_doc_path()})",
        )
    return True, str(persistent_doc_path())


def persistent_doc_path() -> Path:
    return _persistent_discovery_dir() / "drive.v3.json"


def bootstrap_runtime() -> None:
    configure_ssl_certificates()
    configure_drive_discovery_cache()
