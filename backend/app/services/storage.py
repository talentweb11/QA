"""Supabase Storage wrapper for raw bank-statement files.

Files are written to a private bucket; the returned object path is stored in
``bank_statements.storage_path`` and must never be exposed in an API response.
The client is lazily constructed so importing this module does not require the
Supabase env vars to be present (e.g. during unit-test collection).
"""

from __future__ import annotations

from flask import current_app

_client = None


class StorageError(Exception):
    """Raised when a file cannot be stored in Supabase Storage."""


def _get_client():
    global _client
    if _client is not None:
        return _client

    url = current_app.config.get('SUPABASE_URL')
    key = current_app.config.get('SUPABASE_SERVICE_KEY')
    if not url or not key:
        raise StorageError('SUPABASE_URL and SUPABASE_SERVICE_KEY must be configured')

    try:
        from supabase import create_client
    except ImportError as exc:  # pragma: no cover - dependency guard
        raise StorageError('supabase package is not installed') from exc

    _client = create_client(url, key)
    return _client


def upload_statement(object_path: str, file_bytes: bytes, content_type: str) -> str:
    """Upload file bytes to the configured private bucket.

    Returns the object path used as ``storage_path``. Raises StorageError on failure.
    """
    bucket = current_app.config.get('SUPABASE_BUCKET', 'bank-statements')
    client = _get_client()
    try:
        client.storage.from_(bucket).upload(
            path=object_path,
            file=file_bytes,
            file_options={'content-type': content_type, 'upsert': 'false'},
        )
    except Exception as exc:
        raise StorageError(f'Failed to upload statement to storage: {exc}') from exc
    return object_path


def fetch_statement(storage_path: str) -> bytes:
    """Fetch stored file bytes from the configured private bucket.

    Used to retrieve a file for hash verification on download. Raises StorageError on failure.
    """
    bucket = current_app.config.get('SUPABASE_BUCKET', 'bank-statements')
    client = _get_client()
    try:
        response = client.storage.from_(bucket).download(storage_path)
    except Exception as exc:
        raise StorageError(f'Failed to fetch statement from storage: {exc}') from exc
    return response
