from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from app import create_app
from app.middleware import auth as auth_mw
from app.routes import admin as admin_routes


# ---------------------------------------------------------------------------
# Fakes (no real DB — mirrors tests/test_categories.py)
# ---------------------------------------------------------------------------

class _Query:
    """Fake SQLAlchemy query supporting the chain admin.py uses."""

    def __init__(self, result, total=None):
        self.result = result
        self.total = total if total is not None else (
            len(result) if isinstance(result, list) else (0 if result is None else 1)
        )
        self.filter_calls = []

    def filter_by(self, **kwargs):
        self.filter_calls.append(kwargs)
        return self

    def filter(self, *args):
        self.filter_calls.append(args)
        return self

    def order_by(self, *args):
        return self

    def offset(self, *args):
        return self

    def limit(self, *args):
        return self

    def count(self):
        return self.total

    def first(self):
        if isinstance(self.result, list):
            return self.result[0] if self.result else None
        return self.result

    def all(self):
        return self.result if isinstance(self.result, list) else ([] if self.result is None else [self.result])


class _Col:
    """Column expression stand-in supporting .desc() and comparison chaining."""

    def desc(self):
        return self

    def __eq__(self, other):
        return self

    def __ge__(self, other):
        return self

    def __lt__(self, other):
        return self

    def __gt__(self, other):
        return self

    def in_(self, *a):
        return self

    __hash__ = None


class _FakeDbSession:
    def __init__(self):
        self.deleted = []
        self.commit_count = 0

    def add(self, item):
        pass

    def delete(self, item):
        self.deleted.append(item)

    def commit(self):
        self.commit_count += 1

    def rollback(self):
        pass


ADMIN_ID = uuid.UUID('11111111-1111-1111-1111-111111111111')
TARGET_ID = uuid.UUID('22222222-2222-2222-2222-222222222222')


@pytest.fixture
def client():
    app = create_app('development')
    app.config.update(TESTING=True)
    return app.test_client()


def _authenticate(monkeypatch, client, role_name='ADMIN'):
    """Make @require_auth accept the test cookie and bind a fixed current_user."""
    user = SimpleNamespace(id=ADMIN_ID, role_names={role_name})
    session = SimpleNamespace(
        id='sess-1',
        user=user,
        expires_at=datetime.utcnow() + timedelta(hours=1),
        last_active=datetime.utcnow(),
    )
    monkeypatch.setattr(auth_mw, 'Session', SimpleNamespace(query=_Query(session)))
    monkeypatch.setattr(auth_mw, 'db', SimpleNamespace(session=_FakeDbSession()))
    client.set_cookie('session_token', 'test-token')
    return user


def _make_target(status='ACTIVE', role_name='INDIVIDUAL'):
    return SimpleNamespace(
        id=TARGET_ID,
        email='target@example.com',
        display_name='Target User',
        role_names={role_name},
        status=status,
        created_at=datetime(2026, 1, 1),
    )


def _wire(monkeypatch, *, user_result=None, role_result=None, audit_result=None, audit_total=None):
    fake_db = _FakeDbSession()
    events = []
    monkeypatch.setattr(admin_routes, 'db', SimpleNamespace(session=fake_db))
    monkeypatch.setattr(admin_routes, 'User', SimpleNamespace(query=_Query(user_result), created_at=_Col()))
    monkeypatch.setattr(admin_routes, 'Role', SimpleNamespace(query=_Query(role_result), role_name=_Col()))
    monkeypatch.setattr(admin_routes, 'AuditLog', SimpleNamespace(
        query=_Query(audit_result, total=audit_total),
        timestamp=_Col(), event_type=_Col(), user_id=_Col(), outcome=_Col(),
    ))
    monkeypatch.setattr(admin_routes, 'log_event', lambda *a, **k: events.append((a, k)))
    return fake_db, events


# ---------------------------------------------------------------------------
# GET /api/admin/users
# ---------------------------------------------------------------------------

def test_list_users_returns_allowlisted_fields_only(monkeypatch, client):
    _authenticate(monkeypatch, client)
    target = _make_target()
    _wire(monkeypatch, user_result=[target])

    resp = client.get('/api/admin/users')

    assert resp.status_code == 200
    body = resp.get_json()
    assert body == [{
        'id': str(TARGET_ID),
        'email': 'target@example.com',
        'display_name': 'Target User',
        'roles': ['INDIVIDUAL'],
        'status': 'ACTIVE',
        'created_at': '2026-01-01T00:00:00',
    }]
    leaked_fields = {'password_hash', 'totp_secret', 'nric', 'account_number_encrypted', 'email_verification_token_hash'}
    assert not (leaked_fields & body[0].keys())


def test_list_users_requires_admin_role(monkeypatch, client):
    _authenticate(monkeypatch, client, role_name='INDIVIDUAL')
    _wire(monkeypatch, user_result=[])

    resp = client.get('/api/admin/users')

    assert resp.status_code == 403


def test_list_users_requires_auth(client):
    resp = client.get('/api/admin/users')
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# PATCH /api/admin/users/<id>/status
# ---------------------------------------------------------------------------

def test_update_status_success_and_logs(monkeypatch, client):
    _authenticate(monkeypatch, client)
    target = _make_target(status='ACTIVE')
    fake_db, events = _wire(monkeypatch, user_result=target)

    resp = client.patch(f'/api/admin/users/{TARGET_ID}/status', json={'status': 'SUSPENDED'})

    assert resp.status_code == 200
    assert target.status == 'SUSPENDED'
    assert fake_db.commit_count == 1
    assert any(a[0] == 'ADMIN_ACTION' for a, _ in events)


def test_update_status_cannot_target_self(monkeypatch, client):
    _authenticate(monkeypatch, client)
    fake_db, events = _wire(monkeypatch)

    resp = client.patch(f'/api/admin/users/{ADMIN_ID}/status', json={'status': 'SUSPENDED'})

    assert resp.status_code == 403
    assert fake_db.commit_count == 0
    assert events == []


def test_update_status_invalid_value_returns_400(monkeypatch, client):
    _authenticate(monkeypatch, client)
    _wire(monkeypatch, user_result=_make_target())

    resp = client.patch(f'/api/admin/users/{TARGET_ID}/status', json={'status': 'PENDING'})

    assert resp.status_code == 400


def test_update_status_user_not_found_returns_404(monkeypatch, client):
    _authenticate(monkeypatch, client)
    _wire(monkeypatch, user_result=None)

    resp = client.patch(f'/api/admin/users/{TARGET_ID}/status', json={'status': 'SUSPENDED'})

    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /api/admin/users/<id>
# ---------------------------------------------------------------------------

def test_delete_user_success_and_logs(monkeypatch, client):
    _authenticate(monkeypatch, client)
    target = _make_target()
    fake_db, events = _wire(monkeypatch, user_result=target)

    resp = client.delete(f'/api/admin/users/{TARGET_ID}')

    assert resp.status_code == 204
    assert target in fake_db.deleted
    assert any(a[0] == 'ADMIN_ACTION' for a, _ in events)


def test_delete_user_cannot_target_self(monkeypatch, client):
    _authenticate(monkeypatch, client)
    fake_db, events = _wire(monkeypatch)

    resp = client.delete(f'/api/admin/users/{ADMIN_ID}')

    assert resp.status_code == 403
    assert fake_db.deleted == []
    assert events == []


def test_delete_user_not_found_returns_404(monkeypatch, client):
    _authenticate(monkeypatch, client)
    _wire(monkeypatch, user_result=None)

    resp = client.delete(f'/api/admin/users/{TARGET_ID}')

    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# PATCH /api/admin/users/<id>/roles  (a user may hold several roles)
# ---------------------------------------------------------------------------

def test_update_roles_success_and_logs(monkeypatch, client):
    _authenticate(monkeypatch, client)
    target = _make_target(role_name='INDIVIDUAL')
    roles = [SimpleNamespace(id=1, role_name='INDIVIDUAL'),
             SimpleNamespace(id=99, role_name='ADVISOR')]
    fake_db, events = _wire(monkeypatch, user_result=target, role_result=roles)

    resp = client.patch(
        f'/api/admin/users/{TARGET_ID}/roles',
        json={'roles': ['INDIVIDUAL', 'ADVISOR']},
    )

    assert resp.status_code == 200
    assert target.roles == roles
    assert any(a[0] == 'ADMIN_ACTION' for a, _ in events)


def test_update_roles_cannot_target_self(monkeypatch, client):
    _authenticate(monkeypatch, client)
    fake_db, events = _wire(monkeypatch)

    resp = client.patch(f'/api/admin/users/{ADMIN_ID}/roles', json={'roles': ['ADVISOR']})

    assert resp.status_code == 403
    assert events == []


def test_update_roles_empty_list_returns_400(monkeypatch, client):
    _authenticate(monkeypatch, client)
    _wire(monkeypatch, user_result=_make_target())

    resp = client.patch(f'/api/admin/users/{TARGET_ID}/roles', json={'roles': []})

    assert resp.status_code == 400


def test_update_roles_invalid_role_returns_400(monkeypatch, client):
    _authenticate(monkeypatch, client)
    _wire(monkeypatch, user_result=_make_target(), role_result=[])

    resp = client.patch(f'/api/admin/users/{TARGET_ID}/roles', json={'roles': ['NOT_A_ROLE']})

    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# GET /api/admin/audit-logs
# ---------------------------------------------------------------------------

def _make_log(event_type='AUTH_SUCCESS'):
    return SimpleNamespace(
        id=uuid.uuid4(), user_id=ADMIN_ID, event_type=event_type,
        resource_id=None, outcome='SUCCESS', ip_address='127.0.0.1',
        user_agent='pytest', timestamp=datetime(2026, 6, 1, 12, 0, 0),
    )


def test_audit_logs_default_pagination(monkeypatch, client):
    _authenticate(monkeypatch, client)
    logs = [_make_log(), _make_log()]
    _wire(monkeypatch, audit_result=logs, audit_total=2)

    resp = client.get('/api/admin/audit-logs')

    assert resp.status_code == 200
    body = resp.get_json()
    assert body['page'] == 1
    assert body['page_size'] == 50
    assert body['total'] == 2
    assert len(body['items']) == 2


def test_audit_logs_page_size_capped_at_100(monkeypatch, client):
    _authenticate(monkeypatch, client)
    _wire(monkeypatch, audit_result=[], audit_total=0)

    resp = client.get('/api/admin/audit-logs?page_size=500')

    assert resp.status_code == 200
    assert resp.get_json()['page_size'] == 100


def test_audit_logs_requires_admin_role(monkeypatch, client):
    _authenticate(monkeypatch, client, role_name='ADVISOR')
    _wire(monkeypatch, audit_result=[], audit_total=0)

    resp = client.get('/api/admin/audit-logs')

    assert resp.status_code == 403
