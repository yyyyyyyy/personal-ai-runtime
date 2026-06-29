"""Tests for encrypted snapshot sync (AES-GCM export/import)."""

import pytest

# cryptography requires native build (openssl/rust). Skip the whole module if
# the environment cannot provide it — the feature is opt-in and the code paths
# are also exercised via the API layer when the dependency is present.
cryptography = pytest.importorskip("cryptography")

from app.product.encrypted_sync import (  # noqa: E402
    EncryptedSyncError,
    decrypt_snapshot_sync,
    encrypt_snapshot_sync,
)


def test_encrypt_decrypt_roundtrip():
    snapshot = {"event_log": [{"seq": 1, "type": "Test"}], "format": "snapshot"}
    blob = encrypt_snapshot_sync(snapshot, "correct horse battery")
    assert isinstance(blob, str)
    recovered = decrypt_snapshot_sync(blob, "correct horse battery")
    assert recovered == snapshot


def test_wrong_password_rejected():
    blob = encrypt_snapshot_sync({"a": 1}, "the-right-password")
    with pytest.raises(EncryptedSyncError, match="Decryption failed"):
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
    with pytest.raises(EncryptedSyncError, match="Invalid encrypted blob"):
        decrypt_snapshot_sync("!!!not-base64!!!", "somepassword")


def test_truncated_blob_rejected():
    # Too short to contain salt + nonce + tag.
    import base64

    short = base64.b64encode(b"abc").decode()
    with pytest.raises(EncryptedSyncError, match="too short"):
        decrypt_snapshot_sync(short, "somepassword")


def test_each_encryption_uses_fresh_salt_and_nonce():
    blob1 = encrypt_snapshot_sync({"a": 1}, "password123")
    blob2 = encrypt_snapshot_sync({"a": 1}, "password123")
    # Same plaintext + password must still yield different ciphertext because
    # salt and nonce are random per call.
    assert blob1 != blob2
