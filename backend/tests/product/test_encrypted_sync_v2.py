"""Tests for V2 encrypted snapshot sync and V1 backward compatibility."""

import pytest
import base64
import os
import json
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

cryptography = pytest.importorskip("cryptography")

from app.product.encrypted_sync import (
    decrypt_snapshot_sync,
    encrypt_snapshot_sync,
    EncryptedSyncFormatError,
    EncryptedSyncAuthError,
)

def test_v2_roundtrip_with_compression():
    # Large data to test compression
    snapshot = {"data": "A" * 10000, "meta": "test"}
    blob = encrypt_snapshot_sync(snapshot, "password123")
    
    # Check if it starts with magic PAES
    raw = base64.b64decode(blob)
    assert raw.startswith(b"PAES")
    assert raw[4] == 2  # Version
    
    recovered = decrypt_snapshot_sync(blob, "password123")
    assert recovered == snapshot

def test_v1_backward_compatibility():
    # Manually create a V1 blob
    snapshot = {"v1": "legacy data"}
    password = "legacy-password"
    salt = os.urandom(16)
    nonce = os.urandom(12)
    
    # V1 KDF (PBKDF2)
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=600_000,
    )
    key = kdf.derive(password.encode("utf-8"))
    
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(nonce, json.dumps(snapshot).encode("utf-8"), None)
    
    v1_blob = base64.b64encode(salt + nonce + ciphertext).decode("ascii")
    
    # Test decryption of V1 blob
    recovered = decrypt_snapshot_sync(v1_blob, password)
    assert recovered == snapshot

def test_v2_wrong_password():
    blob = encrypt_snapshot_sync({"a": 1}, "correct-password")
    with pytest.raises(EncryptedSyncAuthError):
        decrypt_snapshot_sync(blob, "wrong-password")

def test_v2_unsupported_version():
    # Create a blob with version 99
    blob_raw = b"PAES" + bytes([99]) + os.urandom(16 + 12 + 16)
    blob = base64.b64encode(blob_raw).decode("ascii")
    with pytest.raises(EncryptedSyncFormatError, match="Unsupported blob version"):
        decrypt_snapshot_sync(blob, "password")
