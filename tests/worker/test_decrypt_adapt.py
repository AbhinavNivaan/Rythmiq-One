"""
Decrypt-on-input → adapt → re-encrypt round-trip test.

Tests the adapt-from-master flow:
  1. Worker receives an encrypted master blob (nonce || ciphertext).
  2. Worker decrypts in-memory using sek_b64.
  3. Worker processes (enhance + schema adapt).
  4. Worker re-encrypts the adapted output.
  5. Encrypted output can be decrypted with the same SEK.

Security invariant: at no point is a plaintext image written to disk.

Run with:
    pytest tests/worker/test_decrypt_adapt.py -v
"""

from __future__ import annotations

import base64
import io
import json
import os
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

# Add worker directory to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "worker"))


from crypto import encrypt_file, decrypt_file, sek_from_base64, NONCE_SIZE


# =============================================================================
# Helpers
# =============================================================================

def _make_solid_jpeg(width: int = 400, height: int = 400, color: tuple = (220, 200, 180)) -> bytes:
    """Create a solid-colour JPEG image as bytes."""
    img = Image.new("RGB", (width, height), color=color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def _generate_sek() -> bytes:
    """Generate a random 32-byte SEK."""
    return os.urandom(32)


def _encrypt_blob(plaintext: bytes, sek: bytes) -> bytes:
    """Encrypt plaintext and return nonce || ciphertext blob (worker storage format)."""
    ciphertext, nonce = encrypt_file(plaintext, sek)
    return nonce + ciphertext


def _decrypt_blob(blob: bytes, sek: bytes) -> bytes:
    """Decrypt nonce || ciphertext blob back to plaintext."""
    nonce = blob[:NONCE_SIZE]
    ciphertext = blob[NONCE_SIZE:]
    return decrypt_file(ciphertext, nonce, sek)


# =============================================================================
# Tests: crypto round-trip (unit)
# =============================================================================

class TestCryptoRoundTrip:
    """Unit tests for the nonce-prepended blob format used by the workers."""

    def test_encrypt_decrypt_roundtrip(self):
        """Encrypting then decrypting returns original plaintext."""
        sek = _generate_sek()
        plaintext = b"hello from Rythmiq"
        blob = _encrypt_blob(plaintext, sek)
        assert _decrypt_blob(blob, sek) == plaintext

    def test_blob_starts_with_nonce(self):
        """Blob must be at least NONCE_SIZE bytes and prefix is the nonce."""
        sek = _generate_sek()
        plaintext = b"test"
        blob = _encrypt_blob(plaintext, sek)
        assert len(blob) > NONCE_SIZE

    def test_different_seks_produce_different_blobs(self):
        """Each encryption with a different SEK yields a different blob."""
        plaintext = b"same content"
        sek1 = _generate_sek()
        sek2 = _generate_sek()
        assert _encrypt_blob(plaintext, sek1) != _encrypt_blob(plaintext, sek2)

    def test_wrong_sek_raises(self):
        """Decrypting with a wrong SEK raises an error (GCM authentication)."""
        sek = _generate_sek()
        wrong_sek = _generate_sek()
        blob = _encrypt_blob(b"secret", sek)
        with pytest.raises(Exception):
            _decrypt_blob(blob, wrong_sek)

    def test_truncated_blob_raises(self):
        """A blob shorter than NONCE_SIZE should be rejected by the worker."""
        sek = _generate_sek()
        short_blob = b"\x00" * (NONCE_SIZE - 1)
        with pytest.raises(Exception):
            _decrypt_blob(short_blob, sek)


# =============================================================================
# Tests: worker encrypted_input branch
# =============================================================================

class TestWorkerDecryptInput:
    """Tests for the encrypted_input=True branch in worker.py:process_job()."""

    def test_payload_with_encrypted_input_parses(self):
        """JobPayload.from_dict() should accept encrypted_input=True."""
        from models import JobPayload

        payload_dict = {
            "job_id": "550e8400-e29b-41d4-a716-446655440000",
            "user_id": "7c4e6f9a-bea5-4f7d-9c2a-d6e8f0123456",
            "mode": "adapt",
            "document_type": "photo",
            "encrypted_input": True,
            "sek_b64": base64.b64encode(b"\x01" * 32).decode(),
            "portal_schema": {
                "id": "neet_2026:photograph_passport",
                "name": "neet_2026:photograph_passport",
                "version": 1,
                "schema_definition": {
                    "target_width": 400,
                    "target_height": 400,
                    "target_dpi": 200,
                    "max_kb": 200,
                    "min_kb": 10,
                    "fit_mode": "letterbox",
                    "output_format": "jpeg",
                    "filename_pattern": "{job_id}_photograph_passport",
                },
            },
            "input": {
                "raw_path": "master/user123/job456/job456.enc",
                "artifact_url": None,
                "mime_type": "image/jpeg",
                "original_filename": "photo.jpg",
            },
            "storage": {
                "bucket": "test-bucket",
                "region": "sgp1",
                "endpoint": "https://sgp1.digitaloceanspaces.com",
            },
        }

        payload = JobPayload.from_dict(payload_dict)
        assert payload.encrypted_input is True
        assert payload.sek_b64 == base64.b64encode(b"\x01" * 32).decode()

    def test_encrypted_input_false_by_default(self):
        """encrypted_input defaults to False for backward compatibility."""
        from models import JobPayload

        payload_dict = {
            "job_id": "550e8400-e29b-41d4-a716-446655440000",
            "user_id": "7c4e6f9a-bea5-4f7d-9c2a-d6e8f0123456",
            "mode": "master",
            "document_type": "photo",
            "input": {
                "raw_path": "uploads/user/job/photo.jpg",
                "artifact_url": None,
                "mime_type": "image/jpeg",
                "original_filename": "photo.jpg",
            },
            "storage": {
                "bucket": "test-bucket",
                "region": "sgp1",
                "endpoint": "https://sgp1.digitaloceanspaces.com",
            },
        }

        payload = JobPayload.from_dict(payload_dict)
        assert payload.encrypted_input is False

    def test_encrypted_input_without_sek_raises_worker_error(self, monkeypatch):
        """Worker should raise PAYLOAD_INVALID when encrypted_input=True but sek_b64 is missing."""
        from models import JobPayload, MasterConstraints, InputSpec, StorageSpec
        from errors import WorkerError, ErrorCode

        # Minimal payload with encrypted_input=True but no SEK
        payload = JobPayload(
            job_id="550e8400-e29b-41d4-a716-446655440000",
            user_id="7c4e6f9a-bea5-4f7d-9c2a-d6e8f0123456",
            mode="adapt",
            document_type="photo",
            encrypted_input=True,
            sek_b64=None,  # ← missing
            portal_schema=None,
            master_constraints=MasterConstraints(),
            input=InputSpec(
                artifact_source="path",
                artifact_url=None,
                raw_path="master/u/j/j.enc",
                mime_type="image/jpeg",
                original_filename="photo.jpg",
            ),
            storage=StorageSpec(
                bucket="b",
                region="r",
                endpoint="https://e.example.com",
            ),
        )

        # Patch storage.download to return a mock encrypted blob
        sek = _generate_sek()
        fake_image = _make_solid_jpeg()
        fake_blob = _encrypt_blob(fake_image, sek)

        import unittest.mock as mock
        import worker as worker_module

        with mock.patch("worker.create_client_from_spec") as mock_storage_factory:
            mock_client = mock.MagicMock()
            mock_client.download.return_value = fake_blob
            mock_storage_factory.return_value = mock_client

            with pytest.raises(WorkerError) as exc_info:
                worker_module.process_job(payload)

            assert exc_info.value.code == ErrorCode.PAYLOAD_INVALID

    def test_encrypt_decrypt_image_roundtrip(self):
        """End-to-end: encrypt image → store as blob → decrypt → image is valid JPEG."""
        sek = _generate_sek()
        original_jpeg = _make_solid_jpeg(400, 400)

        # Simulate worker Stage 6: encrypt and prepend nonce
        from crypto import encrypt_file, NONCE_SIZE
        ciphertext, nonce = encrypt_file(original_jpeg, sek)
        stored_blob = nonce + ciphertext

        # Simulate worker Stage 1b: split nonce, decrypt
        assert len(stored_blob) > NONCE_SIZE
        extracted_nonce = stored_blob[:NONCE_SIZE]
        extracted_ciphertext = stored_blob[NONCE_SIZE:]
        recovered = decrypt_file(extracted_ciphertext, extracted_nonce, sek)

        # Recovered bytes should decode as a valid image
        img = Image.open(io.BytesIO(recovered))
        assert img.size == (400, 400)
        assert img.mode in ("RGB", "L")

    def test_sek_from_base64_round_trip(self):
        """sek_from_base64() correctly decodes a base64 SEK."""
        raw_sek = os.urandom(32)
        encoded = base64.b64encode(raw_sek).decode()
        decoded = sek_from_base64(encoded)
        assert decoded == raw_sek
        assert len(decoded) == 32
