"""
Encryption for worker - matches API implementation.

Uses AES-256-GCM for authenticated encryption of processed files
before uploading to storage.
"""

import os
import base64
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


SEK_SIZE = 32
NONCE_SIZE = 12


def encrypt_file(plaintext: bytes, sek: bytes) -> tuple[bytes, bytes]:
    """Encrypt file before storage."""
    if not isinstance(plaintext, bytes):
        raise TypeError("Plaintext must be bytes")
    if len(sek) != SEK_SIZE:
        raise ValueError(f"SEK must be {SEK_SIZE} bytes")

    nonce = os.urandom(NONCE_SIZE)
    cipher = AESGCM(sek)
    ciphertext = cipher.encrypt(nonce, plaintext, None)

    return ciphertext, nonce


def decrypt_file(ciphertext: bytes, nonce: bytes, sek: bytes) -> bytes:
    """Decrypt file from storage."""
    if len(nonce) != NONCE_SIZE:
        raise ValueError(f"Nonce must be {NONCE_SIZE} bytes")
    if len(sek) != SEK_SIZE:
        raise ValueError(f"SEK must be {SEK_SIZE} bytes")

    cipher = AESGCM(sek)
    return cipher.decrypt(nonce, ciphertext, None)


def sek_from_base64(encoded: str) -> bytes:
    """Decode SEK from job payload."""
    return base64.b64decode(encoded.encode('ascii'))


def nonce_to_base64(nonce: bytes) -> str:
    """Encode nonce for storage metadata."""
    return base64.b64encode(nonce).decode('ascii')
