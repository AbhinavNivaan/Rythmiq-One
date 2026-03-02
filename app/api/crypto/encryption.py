"""
Simple encryption-at-rest for Rythmiq Phase 1.

Security Model:
- Files encrypted with user-specific SEK (Storage Encryption Key)
- SEK stored unencrypted in database
- AES-256-GCM for authenticated encryption
- Each file gets a unique random nonce
"""

import os
import base64
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


# Constants
SEK_SIZE = 32      # 256 bits
NONCE_SIZE = 12    # 96 bits (AES-GCM standard)


def generate_sek() -> bytes:
    """
    Generate a random Storage Encryption Key.

    Returns:
        32-byte random SEK
    """
    return os.urandom(SEK_SIZE)


def encrypt_file(plaintext: bytes, sek: bytes) -> tuple[bytes, bytes]:
    """
    Encrypt file with AES-256-GCM.

    Args:
        plaintext: Raw file bytes
        sek: 32-byte Storage Encryption Key

    Returns:
        (ciphertext, nonce) tuple

    Note: Ciphertext includes 16-byte authentication tag appended
    """
    if not isinstance(plaintext, bytes):
        raise TypeError("Plaintext must be bytes")
    if len(sek) != SEK_SIZE:
        raise ValueError(f"SEK must be {SEK_SIZE} bytes, got {len(sek)}")

    nonce = os.urandom(NONCE_SIZE)
    cipher = AESGCM(sek)

    # encrypt() returns ciphertext + 16-byte auth tag
    ciphertext = cipher.encrypt(nonce, plaintext, associated_data=None)

    return ciphertext, nonce


def decrypt_file(ciphertext: bytes, nonce: bytes, sek: bytes) -> bytes:
    """
    Decrypt file with AES-256-GCM.

    Args:
        ciphertext: Encrypted bytes (includes auth tag)
        nonce: 12-byte nonce
        sek: 32-byte Storage Encryption Key

    Returns:
        Plaintext bytes

    Raises:
        cryptography.exceptions.InvalidTag: If file was tampered with
    """
    if not isinstance(ciphertext, bytes):
        raise TypeError("Ciphertext must be bytes")
    if len(nonce) != NONCE_SIZE:
        raise ValueError(f"Nonce must be {NONCE_SIZE} bytes, got {len(nonce)}")
    if len(sek) != SEK_SIZE:
        raise ValueError(f"SEK must be {SEK_SIZE} bytes, got {len(sek)}")

    cipher = AESGCM(sek)

    # decrypt() validates auth tag and returns plaintext
    plaintext = cipher.decrypt(nonce, ciphertext, associated_data=None)

    return plaintext


# Encoding helpers for database storage

def sek_to_base64(sek: bytes) -> str:
    """Encode SEK as base64 for database storage."""
    return base64.b64encode(sek).decode('ascii')


def sek_from_base64(encoded: str) -> bytes:
    """Decode SEK from database."""
    return base64.b64decode(encoded.encode('ascii'))


def nonce_to_base64(nonce: bytes) -> str:
    """Encode nonce as base64 for database storage."""
    return base64.b64encode(nonce).decode('ascii')


def nonce_from_base64(encoded: str) -> bytes:
    """Decode nonce from database."""
    return base64.b64decode(encoded.encode('ascii'))
