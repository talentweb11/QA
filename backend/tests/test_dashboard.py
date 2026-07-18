from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app import create_app
from app.middleware import auth as auth_mw
from app.services import analytics as analytics_svc


# ---------------------------------------------------------------------------
# Fakes (no real DB — mirror tests/test_transactions.py + test_categories.py)
# ---------------------------------------------------------------------------

class _Query:
    """Minimal query used only by @require_auth's Session lookup."""

    def __init__(self, result):
        self.result = result

    def filter_by(self, **kwargs):
        return self

    def filter(self, *args):
        return self

    def first(self):
        return self.result


class _Col:
    """Column expression stub: every comparison / helper returns a throwaway."""

    def isnot(self, *a):
        return self

    def is_(self, *a):
        return self

    def desc(self):
        return self

    def __eq__(self, other):
        return self

    def __ge__(self, other):
        return self

    def __gt__(self, other):
        return self

    def __le__(self, other):
        return self

    def __lt__(self, other):
        return self

    __hash__ = None


class _FakeAggQuery:
    """Chainable stand-in for db.session.query(...); .all() pops the next result set."""

    def __init__(self, session):
        self._session = session

    def join(self, *a, **k):
        return self

    def filter(self, *a, **k):
        return self

    def group_by(self, *a, **k):
        return self

    def order_by(self, *a, **k):
        return self

    def limit(self, *a, **k):
        return self

    def all(self):
        return self._session.next_result()


class _FakeAggSession:
    """Serves preset result sets to successive .query(...).all() calls, in order."""

    def __init__(self, result_sets):
        self._sets = list(result_sets)
        self._i = 0
        self.query_calls = []

    def query(self, *args, **kwargs):
        self.query_calls.append(args)
        return _FakeAggQuery(self)

    def next_result(self):
        r = self._sets[self._i]
        self._i += 1
        return r


USER_ID = uuid.UUID('11111111-1111-1111-1111-111111111111')


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
    monkeypatch.setattr(auth_mw, 'db', SimpleNamespace(session=SimpleNamespace(
        commit=lambda: None, delete=lambda *a: None, rollback=lambda: None,
    )))
    client.set_cookie('session_token', 'test-token')
    return user


def _wire(monkeypatch, *, category_rows, trend_rows, merchant_rows):
    """Point the analytics service's db.session at canned aggregation results.

    The dashboard route delegates to analytics.full_analytics(), so the fakes are
    patched on the analytics module (its single source of truth). Order matters —
    full_analytics() runs: (1) spending_by_category, (2) monthly_trend,
    (3) top_merchants.
    """
    fake_session = _FakeAggSession([category_rows, trend_rows, merchant_rows])
    monkeypatch.setattr(analytics_svc, 'db', SimpleNamespace(session=fake_session))
    # Column expressions are only fed to the fake query (which ignores them),
    # but the service evaluates comparisons like `col >= date` first — so every
    # attribute must be a stub that swallows comparison operators.
    monkeypatch.setattr(analytics_svc, 'Category', SimpleNamespace(name=_Col(), type=_Col(), id=_Col()))
    monkeypatch.setattr(
        analytics_svc, 'Transaction',
        SimpleNamespace(
            user_id=_Col(), category_id=_Col(), amount=_Col(),
            transaction_date=_Col(), merchant_name=_Col(),
        ),
    )
    monkeypatch.setattr(analytics_svc, 'func', SimpleNamespace(
        sum=lambda *a, **k: _Col(),
        to_char=lambda *a, **k: _Col(),
    ))
    return fake_session


# ---------------------------------------------------------------------------
# GET /api/dashboard
# ---------------------------------------------------------------------------

def test_dashboard_shapes_all_three_datasets(monkeypatch, client):
    _authenticate(monkeypatch, client)
    now = datetime.utcnow().date()
    this_month = f'{now.year:04d}-{now.month:02d}'
    _wire(
        monkeypatch,
        category_rows=[('Food', Decimal('120.50')), ('Transport', Decimal('30.00'))],
        trend_rows=[(this_month, 'EXPENSE', Decimal('150.50')),
                    (this_month, 'INCOME', Decimal('2000.00'))],
        merchant_rows=[('Starbucks', Decimal('45.00')), ('Grab', Decimal('30.00'))],
    )

    resp = client.get('/api/dashboard')

    assert resp.status_code == 200
    body = resp.get_json()
    assert body['month'] == this_month
    assert body['spending_by_category'] == [
        {'category': 'Food', 'total': '120.50'},
        {'category': 'Transport', 'total': '30.00'},
    ]
    assert body['top_merchants'][0] == {'merchant': 'Starbucks', 'total': '45.00'}


def test_dashboard_trend_has_six_zero_filled_months(monkeypatch, client):
    _authenticate(monkeypatch, client)
    _wire(monkeypatch, category_rows=[], trend_rows=[], merchant_rows=[])

    resp = client.get('/api/dashboard')

    assert resp.status_code == 200
    trend = resp.get_json()['monthly_trend']
    assert len(trend) == 6
    # Chronological, ending on the current month.
    now = datetime.utcnow().date()
    assert trend[-1]['month'] == f'{now.year:04d}-{now.month:02d}'
    labels = [row['month'] for row in trend]
    assert labels == sorted(labels)
    assert all(row['spend'] == '0' and row['income'] == '0' for row in trend)


def test_dashboard_trend_maps_income_and_spend(monkeypatch, client):
    _authenticate(monkeypatch, client)
    now = datetime.utcnow().date()
    this_month = f'{now.year:04d}-{now.month:02d}'
    _wire(
        monkeypatch,
        category_rows=[],
        trend_rows=[(this_month, 'EXPENSE', Decimal('88.00')),
                    (this_month, 'INCOME', Decimal('3000.00'))],
        merchant_rows=[],
    )

    resp = client.get('/api/dashboard')

    current = [r for r in resp.get_json()['monthly_trend'] if r['month'] == this_month][0]
    assert current['spend'] == '88.00'
    assert current['income'] == '3000.00'


def test_dashboard_empty_user_returns_empty_lists(monkeypatch, client):
    _authenticate(monkeypatch, client)
    _wire(monkeypatch, category_rows=[], trend_rows=[], merchant_rows=[])

    resp = client.get('/api/dashboard')

    body = resp.get_json()
    assert body['spending_by_category'] == []
    assert body['top_merchants'] == []


def test_dashboard_requires_auth(client):
    resp = client.get('/api/dashboard')
    assert resp.status_code == 401
