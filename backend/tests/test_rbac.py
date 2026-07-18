from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from flask import Flask, g, jsonify
from werkzeug.exceptions import Forbidden

from app import create_app
from app.middleware import auth as auth_mw
from app.middleware.auth import assert_owns_resource, require_role
from app.routes import categories as cat_routes
from app.services.consent import get_valid_consent


# ============================================================================
# require_role wired into a real blueprint route (SR-13, end-to-end)
# ============================================================================

class _SessionQuery:
    def __init__(self, session):
        self.session = session

    def filter_by(self, **kwargs):
        return self

    def first(self):
        return self.session


class _NullDbSession:
    def commit(self):
        pass

    def delete(self, *a):
        pass

    def rollback(self):
        pass


class _CategoryQuery:
    """No categories exist — the route only needs to run without a real DB."""

    def filter(self, *args):
        return self

    def order_by(self, *args):
        return self

    def all(self):
        return []


def _client_as(monkeypatch, role_name: str):
    app = create_app('development')
    app.config.update(TESTING=True)
    client = app.test_client()

    user = SimpleNamespace(id=uuid.uuid4(), role_names={role_name})
    session = SimpleNamespace(
        id='sess-1', user=user,
        expires_at=datetime.utcnow() + timedelta(hours=1),
        last_active=datetime.utcnow(),
    )
    monkeypatch.setattr(auth_mw, 'Session', SimpleNamespace(query=_SessionQuery(session)))
    monkeypatch.setattr(auth_mw, 'db', SimpleNamespace(session=_NullDbSession()))
    # GET /api/categories hits Category.query for real past the role gate —
    # stub it out so this test never depends on a live database/schema.
    monkeypatch.setattr(cat_routes, 'Category', SimpleNamespace(
        query=_CategoryQuery(), user_id=SimpleNamespace(is_=lambda *a: None, isnot=lambda *a: None),
        name=None,
    ))
    monkeypatch.setattr(cat_routes, 'or_', lambda *a, **k: None)
    client.set_cookie('session_token', 'test-token')
    return client


def test_require_role_blocks_non_individual_on_real_route(monkeypatch):
    """GET /api/categories is @require_auth + @require_role('INDIVIDUAL') — a
    HOUSEHOLD session must be turned away before any category query runs."""
    client = _client_as(monkeypatch, 'HOUSEHOLD')

    resp = client.get('/api/categories')

    assert resp.status_code == 403
    assert resp.get_json() == {'error': 'Forbidden'}


def test_require_role_admits_individual_on_real_route(monkeypatch):
    """Same route, INDIVIDUAL role, must pass the role check and reach the
    (stubbed) handler — proves the 403 gate doesn't fire for the right role."""
    client = _client_as(monkeypatch, 'INDIVIDUAL')

    resp = client.get('/api/categories')

    assert resp.status_code == 200
    assert resp.get_json() == []


# ============================================================================
# require_role (SR-13)
# ============================================================================

def _app_with_role_route(role_name: str, *allowed_roles: str):
    app = Flask(__name__)
    app.config.update(TESTING=True)

    @app.get('/protected')
    def protected():
        g.current_user = SimpleNamespace(role_names={role_name})
        return require_role(*allowed_roles)(lambda: jsonify(ok=True))()

    app.register_error_handler(403, lambda e: (jsonify(error='Forbidden'), 403))
    return app


def test_require_role_allows_matching_role():
    app = _app_with_role_route('ADMIN', 'ADMIN')
    resp = app.test_client().get('/protected')
    assert resp.status_code == 200
    assert resp.get_json() == {'ok': True}


def test_require_role_allows_one_of_multiple_roles():
    app = _app_with_role_route('ADVISOR', 'ADVISOR', 'INDIVIDUAL')
    resp = app.test_client().get('/protected')
    assert resp.status_code == 200


def test_require_role_rejects_non_matching_role():
    app = _app_with_role_route('HOUSEHOLD', 'ADMIN')
    resp = app.test_client().get('/protected')
    assert resp.status_code == 403
    assert resp.get_json() == {'error': 'Forbidden'}


# ============================================================================
# assert_owns_resource (SR-13)
# ============================================================================

def _app_for_ownership():
    app = Flask(__name__)
    app.config.update(TESTING=True)
    app.register_error_handler(403, lambda e: (jsonify(error='Forbidden'), 403))
    return app


def test_assert_owns_resource_passes_for_matching_owner():
    app = _app_for_ownership()
    user_id = uuid.uuid4()
    with app.test_request_context('/'):
        g.current_user = SimpleNamespace(id=user_id)
        assert_owns_resource(user_id)  # does not raise


def test_assert_owns_resource_raises_403_for_foreign_owner():
    app = _app_for_ownership()
    with app.test_request_context('/'):
        g.current_user = SimpleNamespace(id=uuid.uuid4())
        with pytest.raises(Forbidden):
            assert_owns_resource(uuid.uuid4())


def test_assert_owns_resource_compares_by_string_value():
    """UUID vs. its string form must still be treated as the same owner."""
    app = _app_for_ownership()
    user_id = uuid.uuid4()
    with app.test_request_context('/'):
        g.current_user = SimpleNamespace(id=user_id)
        assert_owns_resource(str(user_id))  # does not raise


# ============================================================================
# get_valid_consent (SR-14)
# ============================================================================

class _ConsentQuery:
    def __init__(self, result):
        self.result = result
        self.filter_args = None

    def filter(self, *args):
        self.filter_args = args
        return self

    def first(self):
        return self.result


class _AlwaysTrueColumn:
    """Column-expression stand-in: every comparison yields a truthy sentinel."""

    def __eq__(self, other):
        return True

    def __gt__(self, other):
        return True

    def is_(self, other):
        return True

    __hash__ = None


def _fake_consent_model(query_result):
    return SimpleNamespace(
        query=_ConsentQuery(query_result),
        grantor_id=_AlwaysTrueColumn(),
        grantee_id=_AlwaysTrueColumn(),
        status=_AlwaysTrueColumn(),
        expires_at=_AlwaysTrueColumn(),
    )


def test_get_valid_consent_returns_active_unexpired_consent(monkeypatch):
    grantor_id, grantee_id = uuid.uuid4(), uuid.uuid4()
    consent = SimpleNamespace(
        grantor_id=grantor_id, grantee_id=grantee_id,
        status='ACTIVE', expires_at=None,
    )
    monkeypatch.setattr('app.services.consent.Consent', _fake_consent_model(consent))

    result = get_valid_consent(grantor_id, grantee_id)

    assert result is consent


def test_get_valid_consent_returns_none_when_no_match(monkeypatch):
    grantor_id, grantee_id = uuid.uuid4(), uuid.uuid4()
    monkeypatch.setattr('app.services.consent.Consent', _fake_consent_model(None))

    result = get_valid_consent(grantor_id, grantee_id)

    assert result is None
