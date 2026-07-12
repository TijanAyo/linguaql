"""Credential encryption (TSD §5)."""
import pytest
from cryptography.fernet import Fernet

from app.config import Settings
from app.utils.crypto import CredentialCipher

URL = "postgresql://demo:s3cr3t@sample-db:5432/shop"


def _cipher(key: str = "") -> CredentialCipher:
    cipher, _ = CredentialCipher.from_settings(Settings(encryption_key=key))
    return cipher


def test_round_trip_reconstructs_url():
    cipher = _cipher()
    enc = cipher.encrypt(URL)
    assert cipher.decrypt_url(enc) == URL


def test_parts_are_encrypted_individually():
    enc = _cipher().encrypt(URL)
    # No plaintext credential appears in any stored ciphertext part.
    for tok in (enc.enc_user, enc.enc_password, enc.enc_host, enc.enc_database):
        assert tok is not None
        assert "demo" not in tok and "s3cr3t" not in tok and "sample-db" not in tok
    # Whole-string encryption is NOT used — parts differ.
    assert enc.enc_user != enc.enc_password


def test_display_masks_password_only():
    enc = _cipher().encrypt(URL)
    assert enc.display == "postgresql://demo:***@sample-db:5432/shop"
    assert "s3cr3t" not in enc.display


def test_host_hash_is_stable_and_not_reversible():
    enc = _cipher().encrypt(URL)
    assert len(enc.host_hash) == 16
    assert "sample-db" not in enc.host_hash
    # host hash is derived from the host only (not the key) -> deterministic
    assert enc.host_hash == _cipher().encrypt(URL).host_hash


def test_wrong_key_cannot_decrypt():
    key_a = Fernet.generate_key().decode()
    key_b = Fernet.generate_key().decode()
    enc = _cipher(key_a).encrypt(URL)
    with pytest.raises(Exception):
        _cipher(key_b).decrypt_url(enc)


def test_persistent_key_round_trips_across_ciphers():
    key = Fernet.generate_key().decode()
    enc = _cipher(key).encrypt(URL)
    # A fresh cipher built from the same key decrypts (survives "restart").
    assert _cipher(key).decrypt_url(enc) == URL


def test_special_characters_in_password_survive():
    url = "postgresql://u%40:p%2Fw%40rd@host:5432/db"  # user "u@", pass "p/w@rd"
    cipher = _cipher()
    assert cipher.decrypt_url(cipher.encrypt(url)) == url
