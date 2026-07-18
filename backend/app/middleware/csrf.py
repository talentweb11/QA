from __future__ import annotations

import hmac
from hashlib import sha256

from flask import current_app, jsonify, request

STATE_CHANGING_METHODS = {'POST', 'PATCH', 'DELETE'}
CSRF_HEADER = 'X-CSRF-Token'

_CSRF_EXEMPT_ENDPOINTS = {
    'auth.login',
    'auth.login_mfa',
    'auth.register',
    'auth.password_reset_request',
    'auth.password_reset_confirm',
}


def generate_csrf_token(session_token: str) -> str:
    secret = current_app.config['SECRET_KEY'].encode('utf-8')
    return hmac.new(secret, session_token.encode('utf-8'), sha256).hexdigest()


def register_csrf_protection(app):
    @app.before_request
    def enforce_csrf_token():
        if current_app.testing:
            return None
        if not current_app.config.get('CSRF_PROTECTION_ENABLED', True):
            return None
        if request.method not in STATE_CHANGING_METHODS:
            return None
        if request.endpoint in current_app.config.get('CSRF_EXEMPT_ENDPOINTS', _CSRF_EXEMPT_ENDPOINTS):
            return None

        session_token = request.cookies.get('session_token')
        if not session_token:
            return None

        expected = generate_csrf_token(session_token)
        submitted = request.headers.get(CSRF_HEADER, '')
        if not hmac.compare_digest(submitted, expected):
            return jsonify({'error': 'Forbidden'}), 403

        return None

    return app
