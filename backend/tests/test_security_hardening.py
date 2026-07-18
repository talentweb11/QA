from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from app import create_app
from app.middleware import auth as auth_mw
from app.middleware.csrf import generate_csrf_token
from app.routes import auth as auth_routes


class _Query:
    def __init__(self, result):
        self.result = result

    def filter_by(self, **kwargs):
        return self

    def first(self):
        return self.result


class _NullDbSession:
    def commit(self):
        pass

    def delete(self, *a):
        pass

    def rollback(self):
        pass


def _authenticated_client(monkeypatch):
    app = create_app('development')
    app.config.update(TESTING=False, CSRF_PROTECTION_ENABLED=True)
    client = app.test_client()

    user = SimpleNamespace(
        id='user-1',
        role_names={'INDIVIDUAL'},
        email='user@example.com',
        display_name='User',
        mfa_enabled=False,
        status='ACTIVE',
    )
    session = SimpleNamespace(
        id='sess-1',
        user=user,
        expires_at=datetime.utcnow() + timedelta(hours=1),
        last_active=datetime.utcnow(),
    )
    monkeypatch.setattr(auth_mw, 'Session', SimpleNamespace(query=_Query(session)))
    monkeypatch.setattr(auth_mw, 'db', SimpleNamespace(session=_NullDbSession()))
    monkeypatch.setattr(auth_routes, 'db', SimpleNamespace(session=_NullDbSession()))
    client.set_cookie('session_token', 'test-token')
    return app, client


def test_security_headers_are_applied():
    client = create_app('development').test_client()

    resp = client.get('/api/health')

    assert resp.headers['Strict-Transport-Security'] == 'max-age=31536000; includeSubDomains'
    assert resp.headers['X-Frame-Options'] == 'DENY'
    assert resp.headers['X-Content-Type-Options'] == 'nosniff'
    assert resp.headers['Content-Security-Policy'] == "default-src 'self'"
    assert resp.headers['Referrer-Policy'] == 'no-referrer'


def test_csrf_endpoint_returns_session_bound_token(monkeypatch):
    app, client = _authenticated_client(monkeypatch)

    resp = client.get('/api/auth/csrf')

    assert resp.status_code == 200
    with app.app_context():
        assert resp.get_json() == {'csrf_token': generate_csrf_token('test-token')}


def test_csrf_blocks_authenticated_mutating_request_without_header(monkeypatch):
    _, client = _authenticated_client(monkeypatch)

    resp = client.post('/api/auth/logout')

    assert resp.status_code == 403
    assert resp.get_json() == {'error': 'Forbidden'}


def test_csrf_allows_authenticated_mutating_request_with_valid_header(monkeypatch):
    app, client = _authenticated_client(monkeypatch)
    with app.app_context():
        token = generate_csrf_token('test-token')

    resp = client.post('/api/auth/logout', headers={'X-CSRF-Token': token})

    assert resp.status_code == 200


def test_generic_json_404_does_not_leak_internal_details():
    client = create_app('development').test_client()

    resp = client.get('/missing-route')

    assert resp.status_code == 404
    assert resp.get_json() == {'error': 'Not found'}


def test_production_config_rejects_missing_secret(monkeypatch):
    from app.config import ProductionConfig

    monkeypatch.setattr(ProductionConfig, 'SECRET_KEY', None)

    with pytest.raises(RuntimeError, match='SECRET_KEY must be set'):
        ProductionConfig.validate()


def test_production_config_rejects_short_secret(monkeypatch):
    from app.config import ProductionConfig

    monkeypatch.setattr(ProductionConfig, 'SECRET_KEY', 'short')

    with pytest.raises(RuntimeError, match='at least 32 bytes'):
        ProductionConfig.validate()
