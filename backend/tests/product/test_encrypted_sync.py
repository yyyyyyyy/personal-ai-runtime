"""Tests for encrypted snapshot sync (AES-GCM export/import).

Covers validation, V2 (PAES) roundtrip, and V1 backward compatibility.
"""

import base64
import json
import os

import pytest

# cryptography requires native build (openssl/rust). Skip the whole module if
# the environment cannot provide it — the feature is opt-in.
pytest.importorskip("cryptography")

from cryptography.hazmat.primitives import hashes  # noqa: E402
from cryptography.hazmat.primitives.ciphers.aead import AESGCM  # noqa: E402
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC  # noqa: E402

from cryptography.hazmat.primitives.kdf.argon2 import Argon2id  # noqa: E402

from app.product import encrypted_sync as enc  # noqa: E402
from app.product.encrypted_sync import (  # noqa: E402
    EncryptedSyncAuthError,
    EncryptedSyncError,
    EncryptedSyncFormatError,
    EncryptedSyncPayloadError,
    decrypt_snapshot,
    decrypt_snapshot_sync,
    encrypt_snapshot,
    encrypt_snapshot_sync,
)


def test_encrypt_decrypt_roundtrip_v2():
    snapshot = {"event_log": [{"seq": 1, "type": "Test"}], "format": "snapshot", "blob": "A" * 1000}
    blob = encrypt_snapshot_sync(snapshot, "correct horse battery")
    assert isinstance(blob, str)
    raw = base64.b64decode(blob)
    assert raw.startswith(b"PAES")
    assert raw[4] == 2
    assert decrypt_snapshot_sync(blob, "correct horse battery") == snapshot


def test_wrong_password_rejected():
    blob = encrypt_snapshot_sync({"a": 1}, "the-right-password")
    with pytest.raises(EncryptedSyncAuthError, match="Decryption failed"):
        decrypt_snapshot_sync(blob, "the-wrong-password")


def test_short_password_rejected():
    with pytest.raises(EncryptedSyncError, match="at least 8"):
        encrypt_snapshot_sync({"a": 1}, "short")


def test_empty_inputs_rejected():
    with pytest.raises(EncryptedSyncError, match="required"):
        decrypt_snapshot_sync("", "somepassword")
    with pytest.raises(EncryptedSyncError, match="required"):
        decrypt_snapshot_sync("abc", "")


def test_malformed_blob_rejected():
    with pytest.raises(EncryptedSyncFormatError, match="Invalid encrypted blob"):
        decrypt_snapshot_sync("!!!not-base64!!!", "somepassword")


def test_truncated_blob_rejected():
    short = base64.b64encode(b"abc").decode()
    with pytest.raises(EncryptedSyncFormatError, match="too short"):
        decrypt_snapshot_sync(short, "somepassword")


def test_each_encryption_uses_fresh_salt_and_nonce():
    blob1 = encrypt_snapshot_sync({"a": 1}, "password123")
    blob2 = encrypt_snapshot_sync({"a": 1}, "password123")
    assert blob1 != blob2


def _v1_key(password: str, salt: bytes) -> bytes:
    return PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=enc._KEY_LEN,
        salt=salt,
        iterations=enc._PBKDF2_ITERATIONS,
    ).derive(password.encode("utf-8"))


def _v2_key(password: str, salt: bytes) -> bytes:
    return Argon2id(
        length=enc._KEY_LEN,
        salt=salt,
        iterations=enc._ARGON2_TIME_COST,
        memory_cost=enc._ARGON2_MEMORY_COST,
        lanes=enc._ARGON2_PARALLELISM,
    ).derive(password.encode("utf-8"))


def test_v1_backward_compatibility():
    snapshot = {"v1": "legacy data"}
    password = "legacy-password"
    salt = os.urandom(enc._SALT_LEN)
    nonce = os.urandom(enc._NONCE_LEN)
    ciphertext = AESGCM(_v1_key(password, salt)).encrypt(
        nonce, json.dumps(snapshot).encode("utf-8"), None
    )
    v1_blob = base64.b64encode(salt + nonce + ciphertext).decode("ascii")

    assert decrypt_snapshot_sync(v1_blob, password) == snapshot


def test_unsupported_version_rejected():
    blob_raw = b"PAES" + bytes([99]) + os.urandom(enc._SALT_LEN + enc._NONCE_LEN + 16)
    blob = base64.b64encode(blob_raw).decode("ascii")
    with pytest.raises(EncryptedSyncFormatError, match="Unsupported blob version"):
        decrypt_snapshot_sync(blob, "password")


def test_truncated_v2_magic_blob_rejected():
    blob = base64.b64encode(b"PAES" + bytes([2]) + b"short").decode("ascii")
    with pytest.raises(EncryptedSyncFormatError, match="too short"):
        decrypt_snapshot_sync(blob, "password12")


def test_v1_invalid_json_payload_rejected():
    password = "legacy-password"
    salt = os.urandom(enc._SALT_LEN)
    nonce = os.urandom(enc._NONCE_LEN)
    ciphertext = AESGCM(_v1_key(password, salt)).encrypt(nonce, b"not-json", None)
    blob = base64.b64encode(salt + nonce + ciphertext).decode("ascii")
    with pytest.raises(EncryptedSyncPayloadError, match="not valid JSON"):
        decrypt_snapshot_sync(blob, password)


def test_v2_decompress_failure_rejected():
    password = "password12"
    salt = os.urandom(enc._SALT_LEN)
    nonce = os.urandom(enc._NONCE_LEN)
    ciphertext = AESGCM(_v2_key(password, salt)).encrypt(nonce, b"not-zlib-payload", None)
    blob = base64.b64encode(b"PAES" + bytes([2]) + salt + nonce + ciphertext).decode("ascii")
    with pytest.raises(EncryptedSyncPayloadError, match="decompress"):
        decrypt_snapshot_sync(blob, password)


@pytest.mark.asyncio
async def test_async_encrypt_decrypt_wrappers():
    snapshot = {"async": True, "n": 1}
    blob = await encrypt_snapshot(snapshot, "password12")
    assert await decrypt_snapshot(blob, "password12") == snapshot
