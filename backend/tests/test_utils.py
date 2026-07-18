import base64
import hashlib
import importlib
import pyotp

from app.utils.crypto import (
    BCRYPT_WORK_FACTOR,
    generate_secure_token,
    generate_totp_secret,
    get_totp_provisioning_uri,
    hash_password,
    validate_password_complexity,
    verify_password,
    verify_totp_code,
)


# ============================================================================
# Encryption Module Helper
# ============================================================================

def _load_module(monkeypatch):
    monkeypatch.setenv('ENCRYPTION_KEY', base64.b64encode(b'0' * 32).decode('ascii'))
    module = importlib.import_module('app.utils.encryption')
    module._get_encryption_key.cache_clear()
    return module


# ============================================================================
# Crypto Tests
# ============================================================================

def test_hash_password_and_verify_password():
    password = "Ocean!Lantern92-Maple"
    hashed = hash_password(password)

    assert hashed != password
    assert hashed.startswith(f"$2b${BCRYPT_WORK_FACTOR}$")
    assert verify_password(password, hashed) is True
    assert verify_password("WrongPassword!123", hashed) is False


def test_password_policy_rejects_short_password():
    valid, reason = validate_password_complexity("Short1!")

    assert valid is False
    assert "12 characters" in reason


def test_password_policy_rejects_weak_common_password():
    valid, reason = validate_password_complexity("Password123!")

    assert valid is False
    assert reason != ""


def test_password_policy_accepts_strong_password():
    valid, reason = validate_password_complexity("Ocean!Lantern92-Maple")

    assert valid is True
    assert reason == ""


def test_password_policy_rejects_bcrypt_truncation_risk():
    valid, reason = validate_password_complexity("A" * 73)

    assert valid is False
    assert "72 bytes" in reason


def test_secure_token_returns_raw_token_and_sha256_hash():
    raw_token, token_hash = generate_secure_token()

    assert raw_token != token_hash
    assert len(raw_token) > 32
    assert token_hash == hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def test_totp_secret_and_provisioning_uri():
    secret = generate_totp_secret()
    uri = get_totp_provisioning_uri("test@example.com", secret)

    assert len(secret) >= 32
    assert uri.startswith("otpauth://totp/")
    assert "issuer=FinTrack" in uri

def test_verify_totp_code_accepts_valid_encrypted_secret(monkeypatch):
    encryption = _load_module(monkeypatch)

    secret = generate_totp_secret()
    encrypted_secret = encryption.encrypt_field(secret)
    valid_code = pyotp.TOTP(secret).now()

    assert verify_totp_code(encrypted_secret, valid_code) is True

def test_verify_totp_code_rejects_wrong_code(monkeypatch):
    encryption = _load_module(monkeypatch)

    secret = generate_totp_secret()
    encrypted_secret = encryption.encrypt_field(secret)
    valid_code = pyotp.TOTP(secret).now()

    wrong_code = valid_code[:-1] + ("0" if valid_code[-1] != "0" else "1")

    assert verify_totp_code(encrypted_secret, wrong_code) is False

# ============================================================================
# Encryption Tests
# ============================================================================

def test_encrypt_and_decrypt_round_trip(monkeypatch):
    encryption = _load_module(monkeypatch)

    ciphertext = encryption.encrypt_field('sensitive-value')

    assert isinstance(ciphertext, str)
    assert encryption.decrypt_field(ciphertext) == 'sensitive-value'


def test_encrypt_field_requires_string(monkeypatch):
    encryption = _load_module(monkeypatch)

    try:
        encryption.encrypt_field(123)
    except TypeError as exc:
        assert 'plaintext must be a string' in str(exc)
    else:
        raise AssertionError('TypeError was not raised')


def test_hash_file_sha256_known_answer(monkeypatch):
    encryption = _load_module(monkeypatch)

    assert encryption.hash_file_sha256(b'abc') == (
        'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad'
    )


def test_hash_file_sha256_requires_bytes_like(monkeypatch):
    encryption = _load_module(monkeypatch)

    try:
        encryption.hash_file_sha256('abc')
    except TypeError as exc:
        assert 'file_bytes must be bytes-like' in str(exc)
    else:
        raise AssertionError('TypeError was not raised')
