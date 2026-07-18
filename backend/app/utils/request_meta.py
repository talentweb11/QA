from __future__ import annotations

from flask import request


def client_ip() -> str:
    """Real client IP. nginx sets X-Real-IP; fall back to Flask's remote_addr."""
    return request.headers.get('X-Real-IP', request.remote_addr) or '0.0.0.0'  # nosec B104


def user_agent() -> str:
    """Client User-Agent, truncated to the audit_logs.user_agent column width."""
    return (request.headers.get('User-Agent') or '')[:500]
