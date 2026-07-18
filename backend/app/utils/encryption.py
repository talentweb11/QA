from __future__ import annotations

import base64
import binascii
import hashlib
import os
from functools import lru_cache

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


_IV_SIZE_BYTES = 12
_TAG_SIZE_BYTES = 16
_KEY_SIZE_BYTES = 32


@lru_cache(maxsize=1)
def _get_encryption_key() -> bytes:
    key_value = os.getenv('ENCRYPTION_KEY')
    if not key_value:
        raise RuntimeError('ENCRYPTION_KEY must be set')

    try:
        decoded_key = base64.b64decode(key_value, validate=True)
    except binascii.Error as exc:
        raw_key = key_value.encode('utf-8')
        if len(raw_key) == _KEY_SIZE_BYTES:
            return raw_key
        raise RuntimeError('ENCRYPTION_KEY must be a base64-encoded 32-byte key') from exc

    if len(decoded_key) != _KEY_SIZE_BYTES:
        raise RuntimeError('ENCRYPTION_KEY must decode to exactly 32 bytes')

    return decoded_key


def encrypt_field(plaintext: str) -> str:
    if not isinstance(plaintext, str):
        raise TypeError('plaintext must be a string')

    iv = os.urandom(_IV_SIZE_BYTES)
    encrypted = AESGCM(_get_encryption_key()).encrypt(iv, plaintext.encode('utf-8'), None)
    ciphertext, tag = encrypted[:-_TAG_SIZE_BYTES], encrypted[-_TAG_SIZE_BYTES:]
    payload = iv + tag + ciphertext
    return base64.b64encode(payload).decode('ascii')


def decrypt_field(ciphertext: str) -> str:
    if not isinstance(ciphertext, str):
        raise TypeError('ciphertext must be a string')

    try:
        payload = base64.b64decode(ciphertext, validate=True)
    except binascii.Error as exc:
        raise ValueError('ciphertext must be valid base64') from exc

    if len(payload) < _IV_SIZE_BYTES + _TAG_SIZE_BYTES:
        raise ValueError('ciphertext payload is too short')

    iv = payload[:_IV_SIZE_BYTES]
    tag = payload[_IV_SIZE_BYTES:_IV_SIZE_BYTES + _TAG_SIZE_BYTES]
    encrypted = payload[_IV_SIZE_BYTES + _TAG_SIZE_BYTES:] + tag
    plaintext = AESGCM(_get_encryption_key()).decrypt(iv, encrypted, None)
    return plaintext.decode('utf-8')


def hash_file_sha256(file_bytes: bytes) -> str:
    if not isinstance(file_bytes, (bytes, bytearray, memoryview)):
        raise TypeError('file_bytes must be bytes-like')

    return hashlib.sha256(bytes(file_bytes)).hexdigest()
