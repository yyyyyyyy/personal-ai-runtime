"""Encrypted snapshot sync — AES-GCM with PBKDF2 (V1) or Argon2id (V2) keys.

Used by the encrypted export/import endpoints. The crypto itself is
intentionally simple and standard, but the CPU-bound derive/encrypt/decrypt
steps are run in a thread executor so the asyncio event loop is not blocked.

V1 Blob layout (Legacy):
    [16 bytes salt][12 bytes nonce][N bytes AES-GCM ciphertext + 16-byte tag]

V2 Blob layout (Current):
    [4 bytes magic 'PAES'][1 byte version=2][16 bytes salt][12 bytes nonce][N bytes AES-GCM encrypted zlib payload]

Import decrypts in-memory, then delegates to Kernel.restore() which
replays events into event_log.
"""

from __future__ import annotations

import asyncio
import base64
import os
import zlib
from typing import Any

try:
    import orjson as json
except ImportError:
    import json

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.argon2 import Argon2id
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

_SALT_LEN = 16
_NONCE_LEN = 12
_KEY_LEN = 32
_PBKDF2_ITERATIONS = 600_000

_MAGIC = b"PAES"
_VERSION_V2 = 2

# Argon2id parameters (OWASP recommendations for general purpose)
_ARGON2_TIME_COST = 3
_ARGON2_MEMORY_COST = 65536  # 64 MiB
_ARGON2_PARALLELISM = 4

MIN_PASSWORD_LEN = 8


class EncryptedSyncError(ValueError):
    """Base exception for encrypted sync failures."""


class EncryptedSyncFormatError(EncryptedSyncError):
    """Raised on malformed blobs or unsupported versions."""


class EncryptedSyncAuthError(EncryptedSyncError):
    """Raised on decryption failure (likely wrong password)."""


class EncryptedSyncPayloadError(EncryptedSyncError):
    """Raised when decrypted payload is invalid (corrupted or not JSON)."""


def _derive_key_v1(password: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=_KEY_LEN,
        salt=salt,
        iterations=_PBKDF2_ITERATIONS,
    )
    return kdf.derive(password.encode("utf-8"))


def _derive_key_v2(password: str, salt: bytes) -> bytes:
    kdf = Argon2id(
        length=_KEY_LEN,
        salt=salt,
        iterations=_ARGON2_TIME_COST,
        memory_cost=_ARGON2_MEMORY_COST,
        lanes=_ARGON2_PARALLELISM,
    )
    return kdf.derive(password.encode("utf-8"))


def encrypt_snapshot_sync(snapshot: dict[str, Any], password: str) -> str:
    """Encrypt ``snapshot`` using V2 format (Argon2id + Zlib + AES-GCM)."""
    if len(password) < MIN_PASSWORD_LEN:
        raise EncryptedSyncError(
            f"Password must be at least {MIN_PASSWORD_LEN} characters"
        )

    # 1. Serialize and compress
    try:
        plaintext = json.dumps(snapshot)
        if isinstance(plaintext, str):
            plaintext = plaintext.encode("utf-8")
    except Exception as exc:
        raise EncryptedSyncPayloadError("Failed to serialize snapshot") from exc

    compressed = zlib.compress(plaintext)

    # 2. Encrypt
    salt = os.urandom(_SALT_LEN)
    nonce = os.urandom(_NONCE_LEN)
    key = _derive_key_v2(password, salt)
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(nonce, compressed, None)

    # 3. Assemble blob: [Magic][Version][Salt][Nonce][Ciphertext]
    blob = _MAGIC + bytes([_VERSION_V2]) + salt + nonce + ciphertext
    return base64.b64encode(blob).decode("ascii")


def decrypt_snapshot_sync(blob: str, password: str) -> dict[str, Any]:
    """Decrypt a base64 blob produced by :func:`encrypt_snapshot_sync`.

    Supports both V1 (legacy) and V2 (compressed Argon2id) formats.
    """
    if not blob or not password:
        raise EncryptedSyncError("data and password are required")

    try:
        raw = base64.b64decode(blob)
    except Exception as exc:
        raise EncryptedSyncFormatError("Invalid encrypted blob format") from exc

    if raw.startswith(_MAGIC):
        return _decrypt_v2(raw, password)
    else:
        return _decrypt_v1(raw, password)


def _decrypt_v1(raw: bytes, password: str) -> dict[str, Any]:
    """Internal: Decrypt V1 legacy format."""
    if len(raw) < _SALT_LEN + _NONCE_LEN + 16:  # 16 = AES-GCM tag
        raise EncryptedSyncFormatError("Encrypted blob is too short")

    salt = raw[:_SALT_LEN]
    nonce = raw[_SALT_LEN:_SALT_LEN + _NONCE_LEN]
    ciphertext = raw[_SALT_LEN + _NONCE_LEN:]

    key = _derive_key_v1(password, salt)
    aesgcm = AESGCM(key)
    try:
        plaintext = aesgcm.decrypt(nonce, ciphertext, None)
    except Exception as exc:
        raise EncryptedSyncAuthError(
            "Decryption failed — wrong password or corrupted data"
        ) from exc

    try:
        return json.loads(plaintext)
    except Exception as exc:
        raise EncryptedSyncPayloadError("Decrypted payload is not valid JSON") from exc


def _decrypt_v2(raw: bytes, password: str) -> dict[str, Any]:
    """Internal: Decrypt V2 modern format."""
    header_len = len(_MAGIC) + 1  # Magic + Version byte
    if len(raw) < header_len + _SALT_LEN + _NONCE_LEN + 16:
        raise EncryptedSyncFormatError("Encrypted blob is too short")

    version = raw[len(_MAGIC)]
    if version != _VERSION_V2:
        raise EncryptedSyncFormatError(f"Unsupported blob version: {version}")

    salt_start = header_len
    nonce_start = salt_start + _SALT_LEN
    cipher_start = nonce_start + _NONCE_LEN

    salt = raw[salt_start:nonce_start]
    nonce = raw[nonce_start:cipher_start]
    ciphertext = raw[cipher_start:]

    key = _derive_key_v2(password, salt)
    aesgcm = AESGCM(key)
    try:
        compressed = aesgcm.decrypt(nonce, ciphertext, None)
    except Exception as exc:
        raise EncryptedSyncAuthError(
            "Decryption failed — wrong password or corrupted data"
        ) from exc

    try:
        plaintext = zlib.decompress(compressed)
    except Exception as exc:
        raise EncryptedSyncPayloadError("Failed to decompress payload") from exc

    try:
        return json.loads(plaintext)
    except Exception as exc:
        raise EncryptedSyncPayloadError("Decrypted payload is not valid JSON") from exc


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


BLOB_FORMAT = "encrypted_snapshot_v2"
