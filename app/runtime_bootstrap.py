"""Frozen-exe and Windows runtime setup (call before Google/HTTPS clients)."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


def _persistent_ca_bundle() -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or str(Path.home())
    return Path(base) / "bgrec" / "cacert.pem"


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


def bootstrap_runtime() -> None:
    configure_ssl_certificates()
