"""Encrypted snapshot sync — AES-GCM with PBKDF2-derived keys.

Used by the encrypted export/import endpoints. The crypto itself is
intentionally simple and standard (PBKDF2-HMAC-SHA256 + AES-GCM), but the
CPU-bound derive/encrypt/decrypt steps are run in a thread executor so the
asyncio event loop is not blocked during large exports/imports.

Blob layout (all binary, base64-encoded at the API boundary):
    [16 bytes salt][12 bytes nonce][N bytes AES-GCM ciphertext + 16-byte tag]

Import decrypts in-memory, then delegates to DigitalLegacy.import_all which
replays events into event_log. That path drops the append-only triggers,
clears, and reinserts — it is a destructive sovereignty operation and the
caller is responsible for requiring the confirm code.
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
from typing import Any

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

_SALT_LEN = 16
_NONCE_LEN = 12
_KEY_LEN = 32
_PBKDF2_ITERATIONS = 600_000
_BLOB_FORMAT = "encrypted_snapshot_v1"

MIN_PASSWORD_LEN = 8


class EncryptedSyncError(ValueError):
    """Raised on malformed blobs or decryption failures."""


def _derive_key(password: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=_KEY_LEN,
        salt=salt,
        iterations=_PBKDF2_ITERATIONS,
    )
    return kdf.derive(password.encode("utf-8"))


def encrypt_snapshot_sync(snapshot: dict[str, Any], password: str) -> str:
    """Encrypt ``snapshot`` and return a base64 blob string.

    Synchronous — wrap with :func:`run_in_executor` from async callers.
    """
    if len(password) < MIN_PASSWORD_LEN:
        raise EncryptedSyncError(
            f"Password must be at least {MIN_PASSWORD_LEN} characters"
        )

    salt = os.urandom(_SALT_LEN)
    key = _derive_key(password, salt)
    nonce = os.urandom(_NONCE_LEN)
    aesgcm = AESGCM(key)
    plaintext = json.dumps(snapshot).encode("utf-8")
    ciphertext = aesgcm.encrypt(nonce, plaintext, None)
    return base64.b64encode(salt + nonce + ciphertext).decode("ascii")


def decrypt_snapshot_sync(blob: str, password: str) -> dict[str, Any]:
    """Decrypt a base64 blob produced by :func:`encrypt_snapshot_sync`.

    Synchronous — wrap with :func:`run_in_executor` from async callers.
    Raises :class:`EncryptedSyncError` on malformed input or wrong password.
    """
    if not blob or not password:
        raise EncryptedSyncError("data and password are required")

    try:
        raw = base64.b64decode(blob)
    except Exception as exc:
        raise EncryptedSyncError("Invalid encrypted blob format") from exc

    if len(raw) < _SALT_LEN + _NONCE_LEN + 16:  # 16 = AES-GCM tag
        raise EncryptedSyncError("Encrypted blob is too short")

    salt = raw[:_SALT_LEN]
    nonce = raw[_SALT_LEN:_SALT_LEN + _NONCE_LEN]
    ciphertext = raw[_SALT_LEN + _NONCE_LEN:]

    key = _derive_key(password, salt)
    aesgcm = AESGCM(key)
    try:
        plaintext = aesgcm.decrypt(nonce, ciphertext, None)
    except Exception as exc:
        raise EncryptedSyncError(
            "Decryption failed — wrong password or corrupted data"
        ) from exc

    try:
        return json.loads(plaintext)
    except json.JSONDecodeError as exc:
        raise EncryptedSyncError("Decrypted payload is not valid JSON") from exc


async def encrypt_snapshot(snapshot: dict[str, Any], password: str) -> str:
    """Async wrapper — runs the CPU-bound crypto in a thread executor."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None, encrypt_snapshot_sync, snapshot, password
    )


async def decrypt_snapshot(blob: str, password: str) -> dict[str, Any]:
    """Async wrapper — runs the CPU-bound crypto in a thread executor."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None, decrypt_snapshot_sync, blob, password
    )


BLOB_FORMAT = _BLOB_FORMAT
