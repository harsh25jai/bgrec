"""AES-256-GCM encryption for audio files before upload."""

from __future__ import annotations

import base64
import os
import secrets
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.logging.setup import get_logger

log = get_logger("encryption")

MAGIC = b"BAR1"  # bgrec encrypted file v1
NONCE_SIZE = 12
KEY_SIZE = 32


class EncryptionManager:
    """Encrypt/decrypt files with AES-256-GCM. Key stored in app data (user profile)."""

    def __init__(self, key_path: Path, enabled: bool = True) -> None:
        self.enabled = enabled
        self.key_path = key_path
        self._key: bytes | None = None
        if enabled:
            self._key = self._load_or_create_key()

    def _load_or_create_key(self) -> bytes:
        self.key_path.parent.mkdir(parents=True, exist_ok=True)
        if self.key_path.exists():
            raw = self.key_path.read_bytes()
            if len(raw) == KEY_SIZE:
                return raw
            # Legacy base64-encoded key
            try:
                decoded = base64.urlsafe_b64decode(raw)
                if len(decoded) == KEY_SIZE:
                    return decoded
            except Exception:
                pass
            log.warning("Invalid key file; generating new key")
        key = secrets.token_bytes(KEY_SIZE)
        self.key_path.write_bytes(key)
        try:
            import stat

            os.chmod(self.key_path, stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass
        log.info("Created new encryption key at {}", self.key_path)
        return key

    @property
    def key(self) -> bytes:
        if not self._key:
            raise RuntimeError("Encryption is disabled")
        return self._key

    def encrypt_file(self, plaintext_path: Path, output_path: Path | None = None) -> Path:
        if not self.enabled:
            raise RuntimeError("Encryption is disabled")
        out = output_path or plaintext_path.with_suffix(plaintext_path.suffix + ".enc")
        data = plaintext_path.read_bytes()
        nonce = secrets.token_bytes(NONCE_SIZE)
        aesgcm = AESGCM(self.key)
        ciphertext = aesgcm.encrypt(nonce, data, None)
        out.write_bytes(MAGIC + nonce + ciphertext)
        log.debug("Encrypted {} -> {}", plaintext_path.name, out.name)
        return out

    def decrypt_file(self, encrypted_path: Path, output_path: Path) -> Path:
        raw = encrypted_path.read_bytes()
        if not raw.startswith(MAGIC):
            raise ValueError(f"Not an encrypted file: {encrypted_path}")
        nonce = raw[len(MAGIC) : len(MAGIC) + NONCE_SIZE]
        ciphertext = raw[len(MAGIC) + NONCE_SIZE :]
        aesgcm = AESGCM(self.key)
        plaintext = aesgcm.decrypt(nonce, ciphertext, None)
        output_path.write_bytes(plaintext)
        return output_path

    def encrypt_bytes(self, data: bytes) -> bytes:
        nonce = secrets.token_bytes(NONCE_SIZE)
        aesgcm = AESGCM(self.key)
        return MAGIC + nonce + aesgcm.encrypt(nonce, data, None)
