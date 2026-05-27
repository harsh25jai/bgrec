"""Google Drive API client with OAuth desktop flow."""

from __future__ import annotations

import json
import threading
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

from app.logging.setup import get_logger

log = get_logger("drive")

SCOPES = ["https://www.googleapis.com/auth/drive.file"]


class DriveClient:
    def __init__(
        self,
        credentials_dir: Path,
        credentials_file: str = "credentials.json",
        token_file: str = "token.json",
        app_folder_name: str = "bgrec",
    ) -> None:
        self.credentials_path = credentials_dir / credentials_file
        self.token_path = credentials_dir / token_file
        self.app_folder_name = app_folder_name
        self._service = None
        self._folder_id: str | None = None
        self._auth_lock = threading.Lock()

    def is_configured(self) -> bool:
        return self.credentials_path.exists()

    def google_auth_status(self) -> tuple[str, str]:
        """
        Return (status_key, human_message) for CLI status.
        Keys: not_configured | not_authenticated | authenticated
        """
        if not self.is_configured():
            return (
                "not_configured",
                "Not set up — add credentials.json and run: bgrec login-google",
            )
        if not self.token_path.exists():
            return (
                "not_authenticated",
                "Not signed in — run: bgrec login-google (recording still works locally)",
            )
        try:
            creds = Credentials.from_authorized_user_file(str(self.token_path), SCOPES)
        except Exception:
            return (
                "not_authenticated",
                "Invalid token — run: bgrec login-google",
            )
        if creds and creds.valid:
            return ("authenticated", "Signed in to Google Drive")
        if creds and creds.expired and creds.refresh_token:
            return ("authenticated", "Signed in (token refreshable)")
        return (
            "not_authenticated",
            "Not signed in — run: bgrec login-google (recording still works locally)",
        )

    def authenticate(self, interactive: bool = True) -> Credentials:
        with self._auth_lock:
            if self._service is not None:
                creds = Credentials.from_authorized_user_file(str(self.token_path), SCOPES)
                if creds and (creds.valid or creds.refresh_token):
                    return creds

            creds: Credentials | None = None
            if self.token_path.exists():
                creds = Credentials.from_authorized_user_file(str(self.token_path), SCOPES)

            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            elif not creds or not creds.valid:
                if not self.credentials_path.exists():
                    raise FileNotFoundError(
                        f"Place OAuth client credentials at: {self.credentials_path}\n"
                        "Download from Google Cloud Console (Desktop app)."
                    )
                if not interactive:
                    raise RuntimeError("Google credentials invalid; run login-google interactively")
                flow = InstalledAppFlow.from_client_secrets_file(str(self.credentials_path), SCOPES)
                creds = flow.run_local_server(port=0)
                self.token_path.parent.mkdir(parents=True, exist_ok=True)
                self.token_path.write_text(creds.to_json(), encoding="utf-8")
                log.info("Google OAuth token saved")

            try:
                self._service = build("drive", "v3", credentials=creds, cache_discovery=False)
            except Exception as exc:
                msg = str(exc).strip()
                if "name:" in msg and "version:" in msg and "drive" in msg.lower():
                    raise RuntimeError(
                        "Google Drive API discovery failed in this build "
                        "(missing API metadata in frozen exe). Reinstall from a newer "
                        "bgrec-Windows.zip or run: bgrec login-google after update."
                    ) from exc
                raise
            return creds

    @property
    def service(self):
        if self._service is None:
            self.authenticate(interactive=False)
        return self._service

    def ensure_app_folder(self) -> str:
        if self._folder_id:
            return self._folder_id
        svc = self.service
        query = (
            f"name='{self.app_folder_name}' and mimeType='application/vnd.google-apps.folder' "
            "and trashed=false"
        )
        result = svc.files().list(q=query, spaces="drive", fields="files(id)").execute()
        files = result.get("files", [])
        if files:
            self._folder_id = files[0]["id"]
        else:
            meta = {"name": self.app_folder_name, "mimeType": "application/vnd.google-apps.folder"}
            created = svc.files().create(body=meta, fields="id").execute()
            self._folder_id = created["id"]
            log.info("Created Drive folder: {}", self.app_folder_name)
        return self._folder_id

    def upload_file(self, local_path: Path, remote_name: str | None = None) -> str:
        folder_id = self.ensure_app_folder()
        name = remote_name or local_path.name
        media = MediaFileUpload(str(local_path), resumable=True)
        meta = {"name": name, "parents": [folder_id]}
        try:
            result = (
                self.service.files()
                .create(body=meta, media_body=media, fields="id,name,size")
                .execute()
            )
            log.bind(upload=True).info(
                "Uploaded {} (id={}, size={})",
                name,
                result.get("id"),
                result.get("size"),
            )
            return result["id"]
        except HttpError as exc:
            log.bind(upload=True).error("Upload failed for {}: {}", name, exc)
            raise

    def revoke_token(self) -> None:
        if self.token_path.exists():
            self.token_path.unlink()
        self._service = None
        self._folder_id = None
