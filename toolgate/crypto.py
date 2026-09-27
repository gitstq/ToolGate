"""Cryptographic helpers.

ToolGate only ever stores *ciphertext* for credentials and only ever stores
*hashes* for tokens.  The primitives used:

* :class:`cryptography.fernet.Fernet` — authenticated symmetric encryption
  (AES-128-CBC + HMAC-SHA256) for credentials at rest.
* :func:`hashlib.sha256` — one-way hashing of gateway / admin tokens.
* :func:`secrets.token_urlsafe` — generation of tokens and key material.

The master key is read from ``TOOLGATE_MASTER_KEY`` when present; otherwise a
32-byte random key is generated once and stored in ``master.key`` inside the
home directory with ``0600`` permissions.
"""
from __future__ import annotations

import hashlib
import os
import secrets
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from .errors import CryptoError


def generate_master_key() -> bytes:
    """Return a fresh URL-safe base64 Fernet key."""
    return Fernet.generate_key()


def load_or_create_master_key(path: Path) -> bytes:
    """Load the master key from disk, creating it on first use.

    The environment variable ``TOOLGATE_MASTER_KEY`` takes precedence over
    the file so that container deployments can inject the key.
    """
    env_key = os.environ.get("TOOLGATE_MASTER_KEY")
    if env_key:
        key = env_key.strip().encode("utf-8")
        _validate_key(key)
        return key

    if path.exists():
        try:
            key = path.read_bytes().strip()
            _validate_key(key)
            return key
        except OSError as exc:
            raise CryptoError(f"Unable to read master key at {path}: {exc}") from exc

    key = generate_master_key()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(key)
        os.chmod(path, 0o600)
    except OSError as exc:
        raise CryptoError(f"Unable to persist master key at {path}: {exc}") from exc
    return key


def _validate_key(key: bytes) -> None:
    try:
        Fernet(key)
    except (ValueError, TypeError) as exc:
        raise CryptoError(
            "Invalid master key: it must be a 32-byte url-safe base64 Fernet key "
            "(generate one with `toolgate keygen`)."
        ) from exc


def generate_token(nbytes: int = 32) -> str:
    """Generate an opaque, URL-safe token shown to the user exactly once."""
    return secrets.token_urlsafe(nbytes)


def hash_token(token: str) -> str:
    """Return the SHA-256 hex digest used to look up a token server-side."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def safe_compare(a: str, b: str) -> bool:
    """Constant-time string comparison."""
    return secrets.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


class Cipher:
    """Thin wrapper around Fernet bound to one master key."""

    def __init__(self, master_key: bytes):
        try:
            self._fernet = Fernet(master_key)
        except (ValueError, TypeError) as exc:
            raise CryptoError("Invalid master key supplied to Cipher.") from exc

    def encrypt(self, plaintext: str) -> str:
        if plaintext is None:
            raise CryptoError("Cannot encrypt None")
        try:
            return self._fernet.encrypt(plaintext.encode("utf-8")).decode("ascii")
        except Exception as exc:  # pragma: no cover - defensive
            raise CryptoError(f"Encryption failed: {exc}") from exc

    def decrypt(self, token: str) -> str:
        try:
            return self._fernet.decrypt(token.encode("ascii")).decode("utf-8")
        except InvalidToken as exc:
            raise CryptoError(
                "Unable to decrypt credential: the master key does not match the "
                "one used when the credential was stored."
            ) from exc
        except Exception as exc:  # pragma: no cover - defensive
            raise CryptoError(f"Decryption failed: {exc}") from exc
