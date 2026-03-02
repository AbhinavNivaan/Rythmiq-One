import pytest
from app.api.crypto.encryption import (
    generate_sek,
    encrypt_file,
    decrypt_file,
    sek_to_base64,
    sek_from_base64,
    nonce_to_base64,
    nonce_from_base64,
)


def test_generate_sek_is_random():
    """SEK should be cryptographically random."""
    sek1 = generate_sek()
    sek2 = generate_sek()

    assert len(sek1) == 32
    assert len(sek2) == 32
    assert sek1 != sek2  # Extremely unlikely to collide


def test_encrypt_decrypt_roundtrip():
    """Encryption and decryption should be reversible."""
    plaintext = b"This is sensitive document data."
    sek = generate_sek()

    ciphertext, nonce = encrypt_file(plaintext, sek)
    decrypted = decrypt_file(ciphertext, nonce, sek)

    assert decrypted == plaintext


def test_ciphertext_is_different_from_plaintext():
    """Ciphertext should not reveal plaintext."""
    plaintext = b"Secret document contents"
    sek = generate_sek()

    ciphertext, nonce = encrypt_file(plaintext, sek)

    assert ciphertext != plaintext
    assert plaintext not in ciphertext  # No plaintext leakage


def test_different_nonces_produce_different_ciphertexts():
    """Same plaintext with different nonces should encrypt differently."""
    plaintext = b"Same plaintext"
    sek = generate_sek()

    ciphertext1, nonce1 = encrypt_file(plaintext, sek)
    ciphertext2, nonce2 = encrypt_file(plaintext, sek)

    assert nonce1 != nonce2
    assert ciphertext1 != ciphertext2


def test_wrong_sek_fails_decryption():
    """Decryption with wrong key should fail."""
    plaintext = b"Sensitive data"
    sek_correct = generate_sek()
    sek_wrong = generate_sek()

    ciphertext, nonce = encrypt_file(plaintext, sek_correct)

    with pytest.raises(Exception):  # InvalidTag from cryptography
        decrypt_file(ciphertext, nonce, sek_wrong)


def test_tampered_ciphertext_fails_decryption():
    """Modified ciphertext should fail authentication."""
    plaintext = b"Original data"
    sek = generate_sek()

    ciphertext, nonce = encrypt_file(plaintext, sek)

    # Tamper with ciphertext
    tampered = bytearray(ciphertext)
    tampered[0] ^= 0xFF  # Flip all bits in first byte

    with pytest.raises(Exception):  # InvalidTag
        decrypt_file(bytes(tampered), nonce, sek)


def test_base64_sek_encoding_roundtrip():
    """SEK should survive base64 encoding for database storage."""
    sek = generate_sek()

    encoded = sek_to_base64(sek)
    decoded = sek_from_base64(encoded)

    assert decoded == sek
    assert isinstance(encoded, str)
    assert len(encoded) == 44  # Base64 of 32 bytes


def test_base64_nonce_encoding_roundtrip():
    """Nonce should survive base64 encoding for database storage."""
    import os
    nonce = os.urandom(12)

    encoded = nonce_to_base64(nonce)
    decoded = nonce_from_base64(encoded)

    assert decoded == nonce
    assert isinstance(encoded, str)
    assert len(encoded) == 16  # Base64 of 12 bytes


def test_encrypt_large_file():
    """Should handle large files (10MB)."""
    plaintext = b"x" * (10 * 1024 * 1024)
    sek = generate_sek()

    ciphertext, nonce = encrypt_file(plaintext, sek)
    decrypted = decrypt_file(ciphertext, nonce, sek)

    assert decrypted == plaintext


def test_empty_file():
    """Should handle empty files."""
    plaintext = b""
    sek = generate_sek()

    ciphertext, nonce = encrypt_file(plaintext, sek)
    decrypted = decrypt_file(ciphertext, nonce, sek)

    assert decrypted == plaintext


def test_invalid_inputs_raise_errors():
    """Should validate inputs."""
    sek = generate_sek()

    # Wrong SEK size
    with pytest.raises(ValueError):
        encrypt_file(b"data", b"short_key")

    # Wrong type
    with pytest.raises(TypeError):
        encrypt_file("not bytes", sek)  # type: ignore[arg-type]

    # Wrong nonce size for decrypt
    with pytest.raises(ValueError):
        decrypt_file(b"data", b"short", sek)

    # Wrong SEK size for decrypt
    with pytest.raises(ValueError):
        decrypt_file(b"data", b"x" * 12, b"short_key")
