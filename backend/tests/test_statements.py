from __future__ import annotations

import io
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app import create_app
from app.middleware import auth as auth_mw
from app.routes import statements as st
from app.services import statement_parser as parser


# ---------------------------------------------------------------------------
# Fakes (no real DB / storage — mirror tests/test_transactions.py)
# ---------------------------------------------------------------------------

class _Query:
    def __init__(self, result):
        self.result = result

    def filter_by(self, **kwargs):
        return self

    def filter(self, *args):
        return self

    def first(self):
        return self.result


class _FakeStatement:
    """Dual-use stand-in for BankStatement: callable constructor (upload path)
    and a `query` class attribute (import path)."""
    query = None

    def __init__(self, **kw):
        self.__dict__.update(kw)
        self.id = kw.get('id') or STMT_ID


class _FakeTxn:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class _FakeDbSession:
    def __init__(self):
        self.added = []
        self.commits = 0
        self.rollbacks = 0

    def add(self, item):
        self.added.append(item)

    def flush(self):
        pass

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


USER_ID = uuid.UUID('11111111-1111-1111-1111-111111111111')
STMT_ID = uuid.UUID('22222222-2222-2222-2222-222222222222')
OTHER_EXP_ID = uuid.UUID('33333333-3333-3333-3333-333333333333')
OTHER_INC_ID = uuid.UUID('44444444-4444-4444-4444-444444444444')


@pytest.fixture
def client():
    app = create_app('development')
    app.config.update(TESTING=True, MAX_UPLOAD_SIZE_MB=10)
    return app.test_client()


def _authenticate(monkeypatch, client):
    user = SimpleNamespace(id=USER_ID, role_names={'INDIVIDUAL'})
    session = SimpleNamespace(
        id='sess-1', user=user,
        expires_at=datetime.utcnow() + timedelta(hours=1),
        last_active=datetime.utcnow(),
    )
    monkeypatch.setattr(auth_mw, 'Session', SimpleNamespace(query=_Query(session)))
    monkeypatch.setattr(auth_mw, 'db', SimpleNamespace(session=SimpleNamespace(
        commit=lambda: None, delete=lambda *a: None, rollback=lambda: None,
    )))
    client.set_cookie('session_token', 'test-token')
    return user


def _row(category_name, *, is_expense=True, amount='10.00', merchant='Shop', desc='d'):
    return {
        'transaction_date': date(2026, 7, 1),
        'amount': Decimal(amount),
        'is_expense': is_expense,
        'merchant_name': merchant,
        'description': desc,
        'category_name': category_name,
    }


def _cat(cat_id=None):
    return SimpleNamespace(id=cat_id or uuid.uuid4())


def _wire_common(monkeypatch):
    """Fake DB + models + storage/hash used by both upload and import paths."""
    fake_db = _FakeDbSession()
    events = []
    monkeypatch.setattr(st, 'db', SimpleNamespace(session=fake_db))
    monkeypatch.setattr(st, 'BankStatement', _FakeStatement)
    monkeypatch.setattr(st, 'Transaction', _FakeTxn)
    monkeypatch.setattr(st, 'log_event', lambda *a, **k: events.append((a, k)))
    monkeypatch.setattr(st, '_other_categories', lambda: (_cat(OTHER_EXP_ID), _cat(OTHER_INC_ID)))
    monkeypatch.setattr(st, 'hash_file_sha256', lambda b: 'HASH')
    return fake_db, events


def _txns(added):
    return [a for a in added if isinstance(a, _FakeTxn)]


def _statements(added):
    return [a for a in added if isinstance(a, _FakeStatement)]


def _upload(client, body=b'date,amount\n2026-07-01,10\n', name='stmt.csv'):
    return client.post(
        '/api/statements/upload',
        data={'file': (io.BytesIO(body), name)},
        content_type='multipart/form-data',
    )


# ---------------------------------------------------------------------------
# Parser — category column
# ---------------------------------------------------------------------------

def test_parser_extracts_category_column():
    csv_bytes = b'date,amount,category,merchant\n2026-07-01,-10.00,Transport,Grab\n'
    rows, skipped = parser.parse_csv(csv_bytes)
    assert skipped == 0
    assert rows[0]['category_name'] == 'Transport'
    assert rows[0]['is_expense'] is True


def test_parser_category_absent_is_none():
    rows, _ = parser.parse_csv(b'date,amount\n2026-07-01,-10.00\n')
    assert rows[0]['category_name'] is None


def test_parser_blank_category_cell_is_none():
    rows, _ = parser.parse_csv(b'date,amount,category\n2026-07-01,-10.00,\n')
    assert rows[0]['category_name'] is None


# ---------------------------------------------------------------------------
# POST /api/statements/upload — analyze
# ---------------------------------------------------------------------------

def test_upload_all_known_imports_immediately(monkeypatch, client):
    _authenticate(monkeypatch, client)
    fake_db, events = _wire_common(monkeypatch)
    monkeypatch.setattr(st, '_uploaded_file_mime_type', lambda f: 'text/csv')
    monkeypatch.setattr(st, 'upload_statement', lambda *a: 'user/obj.csv')
    monkeypatch.setattr(st, 'parse_csv', lambda b: (
        [_row('Transport', is_expense=True), _row(None, is_expense=False)], 1,
    ))
    monkeypatch.setattr(st, '_category_lookup', lambda uid: {'transport': _cat()})

    resp = _upload(client)

    assert resp.status_code == 201
    body = resp.get_json()
    assert body['status'] == 'PROCESSED'
    assert body['imported_count'] == 2
    assert body['skipped_count'] == 1
    assert len(_txns(fake_db.added)) == 2
    assert _statements(fake_db.added)[0].status == 'PROCESSED'
    assert any(a[0] == 'STATEMENT_UPLOADED' and a[1] == 'SUCCESS' for a, _ in events)


def test_upload_unknown_category_holds_pending(monkeypatch, client):
    _authenticate(monkeypatch, client)
    fake_db, events = _wire_common(monkeypatch)
    monkeypatch.setattr(st, '_uploaded_file_mime_type', lambda f: 'text/csv')
    monkeypatch.setattr(st, 'upload_statement', lambda *a: 'user/obj.csv')
    monkeypatch.setattr(st, 'parse_csv', lambda b: (
        [_row('Pet Care', is_expense=True), _row('Side Hustle', is_expense=False)], 0,
    ))
    monkeypatch.setattr(st, '_category_lookup', lambda uid: {})  # nothing known

    resp = _upload(client)

    assert resp.status_code == 201
    body = resp.get_json()
    assert body['status'] == 'NEEDS_CATEGORIES'
    assert body['total_rows'] == 2
    names = {c['name']: c['suggested_type'] for c in body['unknown_categories']}
    assert names == {'Pet Care': 'EXPENSE', 'Side Hustle': 'INCOME'}
    # Nothing imported; statement held as PENDING.
    assert _txns(fake_db.added) == []
    assert _statements(fake_db.added)[0].status == 'PENDING'


def test_upload_unparseable_marks_failed(monkeypatch, client):
    _authenticate(monkeypatch, client)
    fake_db, events = _wire_common(monkeypatch)
    monkeypatch.setattr(st, '_uploaded_file_mime_type', lambda f: 'text/csv')
    monkeypatch.setattr(st, 'upload_statement', lambda *a: 'user/obj.csv')
    monkeypatch.setattr(st, 'parse_csv', lambda b: ([], 0))

    resp = _upload(client)

    assert resp.status_code == 201
    assert resp.get_json()['status'] == 'FAILED'
    assert _txns(fake_db.added) == []
    assert _statements(fake_db.added)[0].status == 'FAILED'


def test_upload_requires_auth(client):
    resp = _upload(client)
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# POST /api/statements/<id>/import — confirm
# ---------------------------------------------------------------------------

def _pending_statement():
    return SimpleNamespace(
        id=STMT_ID, user_id=USER_ID, status='PENDING',
        storage_path='user/obj.csv', file_hash='HASH', file_name='stmt.csv',
    )


def _wire_import(monkeypatch, statement, *, rows, lookup, computed_hash='HASH'):
    fake_db, events = _wire_common(monkeypatch)
    _FakeStatement.query = _Query(statement)
    monkeypatch.setattr(st, 'fetch_statement', lambda path: b'filedata')
    monkeypatch.setattr(st, 'hash_file_sha256', lambda b: computed_hash)
    monkeypatch.setattr(st, 'parse_csv', lambda b: (rows, 0))
    monkeypatch.setattr(st, '_category_lookup', lambda uid: lookup)
    return fake_db, events


def test_import_maps_categories_and_processes(monkeypatch, client):
    _authenticate(monkeypatch, client)
    stmt = _pending_statement()
    fake_db, events = _wire_import(
        monkeypatch, stmt,
        rows=[_row('Pet Care', is_expense=True), _row(None, is_expense=False)],
        lookup={'pet care': _cat()},
    )

    resp = client.post(f'/api/statements/{STMT_ID}/import')

    assert resp.status_code == 200
    body = resp.get_json()
    assert body['status'] == 'PROCESSED'
    assert body['imported_count'] == 2
    assert len(_txns(fake_db.added)) == 2
    assert stmt.status == 'PROCESSED'
    assert any(a[0] == 'STATEMENT_IMPORTED' and a[1] == 'SUCCESS' for a, _ in events)


def test_import_unresolved_category_returns_400(monkeypatch, client):
    _authenticate(monkeypatch, client)
    stmt = _pending_statement()
    fake_db, _ = _wire_import(
        monkeypatch, stmt,
        rows=[_row('Pet Care', is_expense=True)],
        lookup={},  # still missing
    )

    resp = client.post(f'/api/statements/{STMT_ID}/import')

    assert resp.status_code == 400
    assert resp.get_json()['unresolved_categories'] == ['Pet Care']
    assert _txns(fake_db.added) == []
    assert stmt.status == 'PENDING'


def test_import_hash_mismatch_returns_409(monkeypatch, client):
    _authenticate(monkeypatch, client)
    stmt = _pending_statement()
    _wire_import(
        monkeypatch, stmt,
        rows=[_row('Transport')], lookup={'transport': _cat()},
        computed_hash='DIFFERENT',
    )

    resp = client.post(f'/api/statements/{STMT_ID}/import')

    assert resp.status_code == 409
    assert stmt.status == 'PENDING'


def test_import_already_processed_returns_409(monkeypatch, client):
    _authenticate(monkeypatch, client)
    stmt = _pending_statement()
    stmt.status = 'PROCESSED'
    _wire_import(monkeypatch, stmt, rows=[_row('Transport')], lookup={'transport': _cat()})

    resp = client.post(f'/api/statements/{STMT_ID}/import')

    assert resp.status_code == 409


def test_import_foreign_id_returns_404(monkeypatch, client):
    _authenticate(monkeypatch, client)
    _wire_import(monkeypatch, None, rows=[], lookup={})  # query finds nothing

    resp = client.post(f'/api/statements/{STMT_ID}/import')

    assert resp.status_code == 404


def test_import_requires_auth(client):
    resp = client.post(f'/api/statements/{STMT_ID}/import')
    assert resp.status_code == 401
