"""
Shared authentication security utilities for FinTrack.

This module contains password hashing, TOTP helper functions,
password-complexity validation, and secure token generation.
"""

from __future__ import annotations

import binascii
import hashlib
import secrets

import bcrypt
import pyotp
from flask import current_app, has_app_context
from zxcvbn import zxcvbn
from cryptography.exceptions import InvalidTag

BCRYPT_WORK_FACTOR = 12
BCRYPT_MAX_PASSWORD_BYTES = 72
TOTP_DIGITS = 6
TOTP_INTERVAL_SECONDS = 30
DEFAULT_MFA_ISSUER = "FinTrack"


def _get_password_bytes(password: str) -> bytes:
    """Encode a password safely without silently truncating it."""
    if not isinstance(password, str) or not password:
        raise ValueError("Password must be a non-empty string.")

    password_bytes = password.encode("utf-8")

    # bcrypt only supports up to 72 bytes. Reject rather than truncate.
    if len(password_bytes) > BCRYPT_MAX_PASSWORD_BYTES:
        raise ValueError("Password must not exceed 72 bytes.")

    return password_bytes


def hash_password(plaintext: str) -> str:
    """
    Hash a password using bcrypt with a work factor of 12.

    bcrypt.gensalt() creates a unique random salt automatically.
    """
    password_bytes = _get_password_bytes(plaintext)

    return bcrypt.hashpw(
        password_bytes,
        bcrypt.gensalt(rounds=BCRYPT_WORK_FACTOR),
    ).decode("utf-8")


def verify_password(plaintext: str, hashed: str) -> bool:
    """Return True only when the plaintext password matches its bcrypt hash."""
    if not isinstance(plaintext, str) or not isinstance(hashed, str):
        return False

    try:
        password_bytes = _get_password_bytes(plaintext)
        return bcrypt.checkpw(password_bytes, hashed.encode("utf-8"))
    except (TypeError, ValueError):
        return False


def generate_totp_secret() -> str:
    """Generate a Base32 secret for a TOTP authenticator application."""
    return pyotp.random_base32()


def get_totp_provisioning_uri(email: str, secret: str) -> str:
    """
    Generate an otpauth:// URI for QR-code generation during MFA setup.
    """
    if not isinstance(email, str) or not email:
        raise ValueError("Email must be a non-empty string.")

    if not isinstance(secret, str) or not secret:
        raise ValueError("TOTP secret must be a non-empty string.")

    issuer = DEFAULT_MFA_ISSUER
    if has_app_context():
        issuer = current_app.config.get("MFA_ISSUER", DEFAULT_MFA_ISSUER)

    totp = pyotp.TOTP(
        secret,
        digits=TOTP_DIGITS,
        interval=TOTP_INTERVAL_SECONDS,
    )

    return totp.provisioning_uri(name=email, issuer_name=issuer)


def verify_totp_code(encrypted_secret: str, code: str) -> bool:
    """
    Decrypt the stored TOTP secret using HC Y's utility, then verify
    the submitted six-digit TOTP code.

    This requires app.utils.encryption.decrypt_field() to be available.
    """
    if not isinstance(encrypted_secret, str) or not encrypted_secret:
        return False

    if not isinstance(code, str):
        return False

    submitted_code = code.strip()
    if not submitted_code.isdigit() or len(submitted_code) != TOTP_DIGITS:
        return False

    try:
        # Shared AES-256-GCM helper implemented in app.utils.encryption.
        from app.utils.encryption import decrypt_field

        secret = decrypt_field(encrypted_secret)

        if not isinstance(secret, str) or not secret:
            return False

        totp = pyotp.TOTP(
            secret,
            digits=TOTP_DIGITS,
            interval=TOTP_INTERVAL_SECONDS,
        )

        # valid_window=0 accepts only the active 30-second TOTP interval.
        return totp.verify(submitted_code, valid_window=0)

    except (ImportError, ValueError, TypeError, UnicodeDecodeError, binascii.Error, InvalidTag):
        return False


def validate_password_complexity(password: str) -> tuple[bool, str]:
    """
    Check the password policy.

    Requirements:
    - Minimum 12 characters
    - No silent bcrypt truncation
    - Reject weak or common passwords using zxcvbn
    """
    if not isinstance(password, str):
        return False, "Password must be a string."

    if len(password) < 12:
        return False, "Password must be at least 12 characters long."

    if len(password.encode("utf-8")) > BCRYPT_MAX_PASSWORD_BYTES:
        return False, "Password must not exceed 72 bytes."

    strength = zxcvbn(password)

    if strength["score"] < 3:
        return (
            False,
            "Password is too weak or commonly used. Use a longer and less predictable password.",
        )

    return True, ""


def generate_secure_token() -> tuple[str, str]:
    """
    Create a raw URL-safe token and its SHA-256 hash.

    The raw token is for the email link only.
    The SHA-256 hash is what should be stored in the database.
    """
    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

    return raw_token, token_hash