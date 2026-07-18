from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app import create_app
from app.middleware import auth as auth_mw
from app.routes import transactions as txn_routes


# ---------------------------------------------------------------------------
# Fakes (no real DB — mirror the style of test_password_reset.py)
# ---------------------------------------------------------------------------

class _Query:
    """Fake SQLAlchemy query supporting filter_by()/filter().first()."""

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

    def join(self, *args):
        return self

    def order_by(self, *args):
        return self

    def first(self):
        return self.result

    def all(self):
        return self.result if isinstance(self.result, list) else []

    def delete(self, *args, **kwargs):
        return len(self.result) if isinstance(self.result, list) else 0


class _Col:
    """Column expression stub for join()/order_by() argument evaluation."""

    def desc(self):
        return self

    def __eq__(self, other):
        return self

    __hash__ = None


class _FakeDbSession:
    def __init__(self):
        self.added = []
        self.deleted = []
        self.commit_count = 0

    def add(self, item):
        self.added.append(item)

    def delete(self, item):
        self.deleted.append(item)

    def commit(self):
        self.commit_count += 1

    def rollback(self):
        pass


USER_ID = uuid.UUID('11111111-1111-1111-1111-111111111111')
TXN_ID = uuid.UUID('22222222-2222-2222-2222-222222222222')
CAT_ID = uuid.UUID('33333333-3333-3333-3333-333333333333')
NEW_CAT_ID = uuid.UUID('44444444-4444-4444-4444-444444444444')

@pytest.fixture
def client():
    app = create_app('development')
    app.config.update(TESTING=True)
    return app.test_client()


def _make_txn():
    """A mutable transaction with a category relationship for _serialize."""
    cat = SimpleNamespace(id=CAT_ID, name='Food', type='EXPENSE', user_id=None)
    return SimpleNamespace(
        id=TXN_ID,
        user_id=USER_ID,
        category_id=CAT_ID,
        category=cat,
        transaction_date=date(2026, 6, 1),
        amount=Decimal('10.00'),
        merchant_name='Old Shop',
        description='old desc',
    )


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


def _wire_txn(monkeypatch, txn):
    """Point the transactions blueprint at a fake DB and capture audit events."""
    fake_db = _FakeDbSession()
    events = []
    monkeypatch.setattr(txn_routes, 'db', SimpleNamespace(session=fake_db))
    monkeypatch.setattr(txn_routes, 'Transaction', SimpleNamespace(
        query=_Query(txn),
        category_id=_Col(), transaction_date=_Col(), created_at=_Col(),
    ))
    monkeypatch.setattr(txn_routes, 'log_event', lambda *a, **k: events.append((a, k)))
    return fake_db, events


# ---------------------------------------------------------------------------
# PATCH /api/transactions/<id>
# ---------------------------------------------------------------------------

def test_patch_updates_fields_and_logs(monkeypatch, client):
    _authenticate(monkeypatch, client)
    txn = _make_txn()
    fake_db, events = _wire_txn(monkeypatch, txn)

    resp = client.patch(
        f'/api/transactions/{TXN_ID}',
        json={
            'amount': '99.99',
            'merchant_name': 'New Shop',
            'description': None,
            'transaction_date': '2026-06-20',
        }
    )

    assert resp.status_code == 200
    body = resp.get_json()
    assert body['amount'] == '99.99'
    assert body['merchant_name'] == 'New Shop'
    assert body['description'] is None
    assert body['transaction_date'] == '2026-06-20'

    # mutated in place
    assert txn.amount == Decimal('99.99')
    assert txn.description is None
    assert fake_db.commit_count == 1
    assert any(a[0] == 'TRANSACTION_UPDATED' for a, _ in events)


def test_patch_resolves_new_category(monkeypatch, client):
    _authenticate(monkeypatch, client)
    txn = _make_txn()
    _wire_txn(monkeypatch, txn)

    new_cat = SimpleNamespace(id=NEW_CAT_ID, name='Salary', type='INCOME', user_id=None)
    monkeypatch.setattr(txn_routes, '_resolve_category', lambda raw, user: (True, new_cat))

    resp = client.patch(
        f'/api/transactions/{TXN_ID}',
        json={'category_id': str(NEW_CAT_ID)}
    )

    assert resp.status_code == 200
    assert txn.category_id == NEW_CAT_ID


def test_patch_unknown_category_returns_404(monkeypatch, client):
    _authenticate(monkeypatch, client)
    txn = _make_txn()
    _wire_txn(monkeypatch, txn)

    monkeypatch.setattr(
        txn_routes, '_resolve_category',
        lambda raw, user: (False, 'category not found'),
    )

    resp = client.patch(
        f'/api/transactions/{TXN_ID}',
        json={'category_id': str(NEW_CAT_ID)}
    )

    assert resp.status_code == 404


def test_patch_empty_body_returns_400(monkeypatch, client):
    _authenticate(monkeypatch, client)
    txn = _make_txn()
    fake_db, _ = _wire_txn(monkeypatch, txn)

    resp = client.patch(f'/api/transactions/{TXN_ID}', json={})

    assert resp.status_code == 400
    assert fake_db.commit_count == 0


def test_patch_rejects_float_amount(monkeypatch, client):
    _authenticate(monkeypatch, client)
    txn = _make_txn()
    fake_db, _ = _wire_txn(monkeypatch, txn)

    resp = client.patch(
        f'/api/transactions/{TXN_ID}',
        json={'amount': 12.5}
    )

    assert resp.status_code == 400
    assert fake_db.commit_count == 0
    assert txn.amount == Decimal('10.00')  # unchanged


def test_patch_rejects_bad_date(monkeypatch, client):
    _authenticate(monkeypatch, client)
    txn = _make_txn()
    _wire_txn(monkeypatch, txn)

    resp = client.patch(
        f'/api/transactions/{TXN_ID}',
        json={'transaction_date': '20-06-2026'}
    )

    assert resp.status_code == 400


def test_patch_foreign_id_returns_404(monkeypatch, client):
    """Transaction owned by another user -> query returns None -> 404 (IDOR)."""
    _authenticate(monkeypatch, client)
    fake_db, _ = _wire_txn(monkeypatch, None)  # ownership-scoped query finds nothing

    resp = client.patch(
        f'/api/transactions/{TXN_ID}',
        json={'amount': '1.00'}
    )

    assert resp.status_code == 404
    assert fake_db.commit_count == 0


def test_patch_malformed_uuid_returns_404(monkeypatch, client):
    _authenticate(monkeypatch, client)
    _wire_txn(monkeypatch, _make_txn())

    resp = client.patch(
        '/api/transactions/not-a-uuid',
        json={'amount': '1.00'}
    )

    assert resp.status_code == 404


def test_patch_requires_auth(client):
    resp = client.patch(
        f'/api/transactions/{TXN_ID}',
        json={'amount': '1.00'},
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# DELETE /api/transactions/<id>
# ---------------------------------------------------------------------------

def test_delete_removes_and_logs(monkeypatch, client):
    _authenticate(monkeypatch, client)
    txn = _make_txn()
    fake_db, events = _wire_txn(monkeypatch, txn)

    resp = client.delete(f'/api/transactions/{TXN_ID}')

    assert resp.status_code == 204
    assert resp.data == b''
    assert txn in fake_db.deleted
    assert fake_db.commit_count == 1
    assert any(a[0] == 'TRANSACTION_DELETED' for a, _ in events)


def test_delete_foreign_id_returns_404(monkeypatch, client):
    _authenticate(monkeypatch, client)
    fake_db, events = _wire_txn(monkeypatch, None)

    resp = client.delete(f'/api/transactions/{TXN_ID}')

    assert resp.status_code == 404
    assert fake_db.deleted == []
    assert not any(a[0] == 'TRANSACTION_DELETED' for a, _ in events)


def test_delete_malformed_uuid_returns_404(monkeypatch, client):
    _authenticate(monkeypatch, client)
    _wire_txn(monkeypatch, _make_txn())

    resp = client.delete('/api/transactions/not-a-uuid')

    assert resp.status_code == 404


def test_delete_requires_auth(client):
    resp = client.delete(f'/api/transactions/{TXN_ID}')
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# DELETE /api/transactions (bulk clear)
# ---------------------------------------------------------------------------

def test_delete_all_clears_and_logs(monkeypatch, client):
    _authenticate(monkeypatch, client)
    fake_db, events = _wire_txn(monkeypatch, [_make_txn(), _make_txn(), _make_txn()])

    resp = client.delete('/api/transactions')

    assert resp.status_code == 200
    assert resp.get_json()['deleted_count'] == 3
    assert fake_db.commit_count == 1
    assert any(a[0] == 'TRANSACTIONS_CLEARED' for a, _ in events)


def test_delete_all_requires_auth(client):
    resp = client.delete('/api/transactions')
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/transactions/export (FR-13)
# ---------------------------------------------------------------------------

def _make_txn_with(merchant='Shop A', description='desc', name='Food'):
    cat = SimpleNamespace(id=CAT_ID, name=name, type='EXPENSE', user_id=None)
    return SimpleNamespace(
        id=uuid.uuid4(),
        user_id=USER_ID,
        category_id=CAT_ID,
        category=cat,
        transaction_date=date(2026, 6, 1),
        amount=Decimal('10.00'),
        merchant_name=merchant,
        description=description,
    )


def test_export_returns_csv_with_header_and_rows(monkeypatch, client):
    _authenticate(monkeypatch, client)
    txns = [_make_txn_with(merchant='Shop A'), _make_txn_with(merchant='Shop B')]
    _wire_txn(monkeypatch, txns)

    resp = client.get('/api/transactions/export')

    assert resp.status_code == 200
    assert resp.headers['Content-Type'].startswith('text/csv')
    assert resp.headers['Content-Disposition'] == 'attachment; filename="transactions.csv"'

    lines = resp.get_data(as_text=True).strip().splitlines()
    assert lines[0] == 'date,amount,category,merchant,description'
    assert len(lines) == 3  # header + 2 rows
    assert '2026-06-01,10.00,Food,Shop A,desc' in lines


def test_export_empty_has_only_header(monkeypatch, client):
    _authenticate(monkeypatch, client)
    _wire_txn(monkeypatch, [])

    resp = client.get('/api/transactions/export')

    assert resp.status_code == 200
    lines = resp.get_data(as_text=True).strip().splitlines()
    assert lines == ['date,amount,category,merchant,description']


def test_export_sanitises_formula_injection(monkeypatch, client):
    _authenticate(monkeypatch, client)
    txn = _make_txn_with(merchant='=SUM(A1:A9)', description='+HYPERLINK("x")')
    _wire_txn(monkeypatch, [txn])

    resp = client.get('/api/transactions/export')

    body = resp.get_data(as_text=True)
    # csv.writer quotes the cell because it contains a comma; the leading
    # apostrophe defuses the formula regardless of quoting.
    assert "'=SUM(A1:A9)" in body
    assert "'+HYPERLINK" in body


def test_export_logs_audit_event(monkeypatch, client):
    _authenticate(monkeypatch, client)
    _, events = _wire_txn(monkeypatch, [_make_txn_with()])

    client.get('/api/transactions/export')

    assert any(a[0] == 'TRANSACTION_EXPORTED' for a, _ in events)


def test_export_requires_auth(client):
    resp = client.get('/api/transactions/export')
    assert resp.status_code == 401
