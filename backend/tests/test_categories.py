from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy.exc import IntegrityError

from app import create_app
from app.middleware import auth as auth_mw
from app.routes import categories as cat_routes


# ---------------------------------------------------------------------------
# Fakes (no real DB — mirror tests/test_transactions.py)
# ---------------------------------------------------------------------------

class _Query:
    """Fake SQLAlchemy query supporting filter_by()/filter().order_by().first()/all()."""

    def __init__(self, result):
        self.result = result
        self.filter_by_calls = []
        self.filter_calls = []

    def filter_by(self, **kwargs):
        self.filter_by_calls.append(kwargs)
        return self

    def filter(self, *args):
        self.filter_calls.append(args)
        return self

    def order_by(self, *args):
        return self

    def first(self):
        if isinstance(self.result, list):
            return self.result[0] if self.result else None
        return self.result

    def all(self):
        return self.result if isinstance(self.result, list) else [self.result]


class _FakeColumn:
    """Stand-in for a SQLAlchemy column expression used in filter/order_by."""

    def is_(self, *a):
        return self

    def isnot(self, *a):
        return self

    def __eq__(self, other):
        return self

    __hash__ = None


def _make_category_model(query_result):
    class FakeCategory:
        query = _Query(query_result)
        user_id = _FakeColumn()
        id = _FakeColumn()
        name = _FakeColumn()

        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)
            if 'id' not in kwargs:
                self.id = CAT_ID

    return FakeCategory


class _FakeDbSession:
    def __init__(self, commit_error=None):
        self.added = []
        self.deleted = []
        self.commit_count = 0
        self.rolled_back = 0
        self._commit_error = commit_error

    def add(self, item):
        self.added.append(item)

    def delete(self, item):
        self.deleted.append(item)

    def commit(self):
        self.commit_count += 1
        if self._commit_error is not None:
            raise self._commit_error

    def rollback(self):
        self.rolled_back += 1


USER_ID = uuid.UUID('11111111-1111-1111-1111-111111111111')
CAT_ID = uuid.UUID('33333333-3333-3333-3333-333333333333')


@pytest.fixture
def client():
    app = create_app('development')
    app.config.update(TESTING=True)
    return app.test_client()


def _authenticate(monkeypatch, client):
    """Make @require_auth accept the test cookie and bind a fixed current_user."""
    user = SimpleNamespace(id=USER_ID, role_names={'INDIVIDUAL'})
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


def _make_category(user_id=USER_ID, name='Coffee', ctype='EXPENSE'):
    return SimpleNamespace(id=CAT_ID, user_id=user_id, name=name, type=ctype)


def _wire(monkeypatch, *, category_result=None, txn_result=None, commit_error=None):
    """Point the categories blueprint at fakes and capture audit events."""
    fake_db = _FakeDbSession(commit_error=commit_error)
    events = []
    monkeypatch.setattr(cat_routes, 'db', SimpleNamespace(session=fake_db))
    monkeypatch.setattr(cat_routes, 'Category', _make_category_model(category_result))
    monkeypatch.setattr(cat_routes, 'Transaction', SimpleNamespace(query=_Query(txn_result)))
    monkeypatch.setattr(cat_routes, 'or_', lambda *a, **k: None)
    monkeypatch.setattr(cat_routes, 'log_event', lambda *a, **k: events.append((a, k)))
    return fake_db, events


# ---------------------------------------------------------------------------
# GET /api/categories
# ---------------------------------------------------------------------------

def test_get_lists_global_and_custom_with_labels(monkeypatch, client):
    _authenticate(monkeypatch, client)
    cats = [
        SimpleNamespace(id=uuid.uuid4(), user_id=None, name='Groceries', type='EXPENSE'),
        SimpleNamespace(id=CAT_ID, user_id=USER_ID, name='Coffee', type='EXPENSE'),
    ]
    _wire(monkeypatch, category_result=cats)

    resp = client.get('/api/categories')

    assert resp.status_code == 200
    body = resp.get_json()
    assert body[0]['is_global'] is True
    assert body[1]['is_global'] is False
    assert body[1]['name'] == 'Coffee'


def test_get_requires_auth(client):
    resp = client.get('/api/categories')
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# POST /api/categories
# ---------------------------------------------------------------------------

def test_post_creates_and_logs(monkeypatch, client):
    _authenticate(monkeypatch, client)
    fake_db, events = _wire(monkeypatch)

    resp = client.post('/api/categories', json={'name': 'Coffee', 'type': 'EXPENSE'})

    assert resp.status_code == 201
    body = resp.get_json()
    assert body['name'] == 'Coffee'
    assert body['type'] == 'EXPENSE'
    assert body['is_global'] is False
    assert len(fake_db.added) == 1
    assert fake_db.commit_count == 1
    assert any(a[0] == 'CATEGORY_CREATED' for a, _ in events)


def test_post_duplicate_name_returns_409(monkeypatch, client):
    _authenticate(monkeypatch, client)
    fake_db, events = _wire(monkeypatch, commit_error=IntegrityError('dup', None, Exception()))

    resp = client.post('/api/categories', json={'name': 'Coffee', 'type': 'EXPENSE'})

    assert resp.status_code == 409
    assert fake_db.rolled_back == 1
    assert not any(a[0] == 'CATEGORY_CREATED' for a, _ in events)


def test_post_invalid_type_returns_400(monkeypatch, client):
    _authenticate(monkeypatch, client)
    fake_db, _ = _wire(monkeypatch)

    resp = client.post('/api/categories', json={'name': 'Coffee', 'type': 'SAVINGS'})

    assert resp.status_code == 400
    assert fake_db.commit_count == 0


def test_post_empty_name_returns_400(monkeypatch, client):
    _authenticate(monkeypatch, client)
    fake_db, _ = _wire(monkeypatch)

    resp = client.post('/api/categories', json={'name': '   ', 'type': 'EXPENSE'})

    assert resp.status_code == 400
    assert fake_db.commit_count == 0


def test_post_requires_auth(client):
    resp = client.post('/api/categories', json={'name': 'Coffee', 'type': 'EXPENSE'})
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# DELETE /api/categories/<id>
# ---------------------------------------------------------------------------

def test_delete_own_unused_returns_204_and_logs(monkeypatch, client):
    _authenticate(monkeypatch, client)
    category = _make_category()
    fake_db, events = _wire(monkeypatch, category_result=category, txn_result=None)

    resp = client.delete(f'/api/categories/{CAT_ID}')

    assert resp.status_code == 204
    assert resp.data == b''
    assert category in fake_db.deleted
    assert fake_db.commit_count == 1
    assert any(a[0] == 'CATEGORY_DELETED' for a, _ in events)


def test_delete_in_use_returns_409(monkeypatch, client):
    _authenticate(monkeypatch, client)
    category = _make_category()
    referencing_txn = SimpleNamespace(id=uuid.uuid4(), category_id=CAT_ID)
    fake_db, events = _wire(monkeypatch, category_result=category, txn_result=referencing_txn)

    resp = client.delete(f'/api/categories/{CAT_ID}')

    assert resp.status_code == 409
    assert fake_db.deleted == []
    assert fake_db.commit_count == 0
    assert not any(a[0] == 'CATEGORY_DELETED' for a, _ in events)


def test_delete_global_or_foreign_returns_404(monkeypatch, client):
    """Scoped query returns None for a global/other-user category."""
    _authenticate(monkeypatch, client)
    fake_db, _ = _wire(monkeypatch, category_result=None)

    resp = client.delete(f'/api/categories/{CAT_ID}')

    assert resp.status_code == 404
    assert fake_db.deleted == []


def test_delete_malformed_uuid_returns_404(monkeypatch, client):
    _authenticate(monkeypatch, client)
    _wire(monkeypatch, category_result=_make_category())

    resp = client.delete('/api/categories/not-a-uuid')

    assert resp.status_code == 404


def test_delete_requires_auth(client):
    resp = client.delete(f'/api/categories/{CAT_ID}')
    assert resp.status_code == 401
