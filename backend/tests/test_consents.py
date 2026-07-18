from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from app import create_app
from app.middleware import auth as auth_mw
from app.routes import consents as consent_routes


# ---------------------------------------------------------------------------
# Fakes (no real DB — mirrors the style of test_transactions.py)
# ---------------------------------------------------------------------------

class _Query:
    """Fake SQLAlchemy query supporting filter_by()/filter().first()/all()."""

    def __init__(self, result):
        self.result = result

    def filter_by(self, **kwargs):
        return self

    def filter(self, *args):
        return self

    def first(self):
        return self.result

    def all(self):
        return self.result if isinstance(self.result, list) else []


class _Col:
    """Column-expression stub so filter()/or_() argument building doesn't raise."""

    def __eq__(self, other):
        return self

    def __gt__(self, other):
        return self

    def is_(self, other):
        return self

    __hash__ = None


class _FakeDbSession:
    def __init__(self):
        self.added = []
        self.commit_count = 0

    def add(self, item):
        self.added.append(item)

    def commit(self):
        self.commit_count += 1

    def rollback(self):
        pass


GRANTOR_ID = uuid.UUID('11111111-1111-1111-1111-111111111111')
GRANTEE_ID = uuid.UUID('22222222-2222-2222-2222-222222222222')
CONSENT_ID = uuid.UUID('33333333-3333-3333-3333-333333333333')

GRANTOR_EMAIL = 'individual@example.com'
GRANTEE_EMAIL = 'household@example.com'


@pytest.fixture
def client():
    app = create_app('development')
    app.config.update(TESTING=True)
    return app.test_client()


def _authenticate(monkeypatch, client, role='INDIVIDUAL'):
    """Make @require_auth accept the test cookie and bind a fixed current_user."""
    user = SimpleNamespace(
        id=GRANTOR_ID,
        email=GRANTOR_EMAIL,
        display_name='Ivy Individual',
        role_names={role},
    )
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


def _make_grantee(role='HOUSEHOLD', status='ACTIVE'):
    return SimpleNamespace(
        id=GRANTEE_ID,
        email=GRANTEE_EMAIL,
        display_name='Hank Household',
        status=status,
        role_names={role},
        has_role=lambda name, _roles={role}: name in _roles,
    )


def _make_existing(access_level='SUMMARY_ONLY', status='REVOKED'):
    """An existing consent row the (grantor, grantee) lookup will return."""
    return SimpleNamespace(
        id=CONSENT_ID,
        grantor_id=GRANTOR_ID,
        grantee_id=GRANTEE_ID,
        grantee=_make_grantee(),
        access_level=access_level,
        status=status,
        expires_at=None,
        created_at=datetime(2026, 1, 1),
        updated_at=datetime(2026, 1, 1),
    )


def _wire(monkeypatch, grantee, existing):
    """Point the consents blueprint at fakes; capture audit events + emails."""
    fake_db = _FakeDbSession()
    events = []
    sent = []

    class _FakeConsent:
        query = _Query(existing)
        grantor_id = _Col()
        grantee_id = _Col()
        access_level = _Col()
        status = _Col()
        expires_at = _Col()

        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)
            self.id = CONSENT_ID
            self.created_at = datetime.utcnow()
            self.updated_at = None
            self.grantee = None  # relationship not populated without a real flush

    monkeypatch.setattr(consent_routes, 'db', SimpleNamespace(session=fake_db))
    monkeypatch.setattr(consent_routes, 'User', SimpleNamespace(query=_Query(grantee)))
    monkeypatch.setattr(consent_routes, 'Consent', _FakeConsent)
    monkeypatch.setattr(consent_routes, 'log_event', lambda *a, **k: events.append((a, k)))
    monkeypatch.setattr(consent_routes, 'send_consent_notification',
                        lambda *a, **k: sent.append((a, k)))
    return fake_db, events, sent


# ---------------------------------------------------------------------------
# POST /api/consents/household — happy paths
# ---------------------------------------------------------------------------

def test_grant_creates_consent(monkeypatch, client):
    _authenticate(monkeypatch, client)
    fake_db, events, sent = _wire(monkeypatch, _make_grantee(), existing=None)

    resp = client.post('/api/consents/household', json={'grantee_email': GRANTEE_EMAIL})

    assert resp.status_code == 201
    body = resp.get_json()
    assert body['access_level'] == 'SUMMARY_ONLY'
    assert body['status'] == 'ACTIVE'
    assert len(fake_db.added) == 1            # a new consent row was inserted
    assert fake_db.commit_count == 1
    assert any(a[0] == 'CONSENT_GRANTED' and a[1] == 'SUCCESS' for a, _ in events)
    assert len(sent) == 1                     # grantee was emailed


def test_grant_reactivates_revoked_consent(monkeypatch, client):
    _authenticate(monkeypatch, client)
    existing = _make_existing(status='REVOKED')
    fake_db, events, sent = _wire(monkeypatch, _make_grantee(), existing=existing)

    resp = client.post('/api/consents/household', json={'grantee_email': GRANTEE_EMAIL})

    assert resp.status_code == 201
    assert existing.status == 'ACTIVE'        # reactivated in place
    assert existing.expires_at is None
    assert fake_db.added == []                # no new row inserted
    assert fake_db.commit_count == 1
    assert any(a[0] == 'CONSENT_GRANTED' and a[1] == 'SUCCESS' for a, _ in events)


# ---------------------------------------------------------------------------
# GET /api/consents/household — list my active shares
# ---------------------------------------------------------------------------

def test_list_household_shares_returns_active(monkeypatch, client):
    _authenticate(monkeypatch, client)
    shares = [_make_existing(status='ACTIVE')]
    _wire(monkeypatch, grantee=None, existing=shares)

    resp = client.get('/api/consents/household')

    assert resp.status_code == 200
    body = resp.get_json()
    assert len(body['shares']) == 1
    assert body['shares'][0]['grantee_email'] == GRANTEE_EMAIL
    assert body['shares'][0]['access_level'] == 'SUMMARY_ONLY'


def test_list_household_shares_requires_individual(monkeypatch, client):
    _authenticate(monkeypatch, client, role='HOUSEHOLD')
    _wire(monkeypatch, grantee=None, existing=[])

    resp = client.get('/api/consents/household')

    assert resp.status_code == 403


def test_list_household_shares_requires_auth(client):
    resp = client.get('/api/consents/household')
    assert resp.status_code == 401


def test_list_advisor_shares_returns_active(monkeypatch, client):
    _authenticate(monkeypatch, client)
    shares = [_make_existing(access_level='FULL_VIEW', status='ACTIVE')]
    _wire(monkeypatch, grantee=None, existing=shares)

    resp = client.get('/api/consents/advisor')

    assert resp.status_code == 200
    body = resp.get_json()
    assert len(body['shares']) == 1
    assert body['shares'][0]['access_level'] == 'FULL_VIEW'


# ---------------------------------------------------------------------------
# POST /api/consents/household — conflicts and rejections
# ---------------------------------------------------------------------------

def test_grant_already_active_returns_409(monkeypatch, client):
    _authenticate(monkeypatch, client)
    existing = _make_existing(status='ACTIVE')
    fake_db, _, _ = _wire(monkeypatch, _make_grantee(), existing=existing)

    resp = client.post('/api/consents/household', json={'grantee_email': GRANTEE_EMAIL})

    assert resp.status_code == 409
    assert fake_db.commit_count == 0


def test_grant_conflicting_advisor_consent_returns_409(monkeypatch, client):
    _authenticate(monkeypatch, client)
    existing = _make_existing(access_level='FULL_VIEW', status='ACTIVE')
    fake_db, events, _ = _wire(monkeypatch, _make_grantee(), existing=existing)

    resp = client.post('/api/consents/household', json={'grantee_email': GRANTEE_EMAIL})

    assert resp.status_code == 409
    assert fake_db.commit_count == 0
    assert any(a[0] == 'CONSENT_GRANTED' and a[1] == 'FAILURE' for a, _ in events)


def test_grant_to_self_returns_400(monkeypatch, client):
    _authenticate(monkeypatch, client)
    fake_db, events, _ = _wire(monkeypatch, _make_grantee(), existing=None)

    resp = client.post('/api/consents/household', json={'grantee_email': GRANTOR_EMAIL})

    assert resp.status_code == 400
    assert fake_db.commit_count == 0
    assert any(a[0] == 'CONSENT_GRANTED' and a[1] == 'FAILURE' for a, _ in events)


def test_grant_unknown_grantee_returns_404(monkeypatch, client):
    _authenticate(monkeypatch, client)
    fake_db, events, _ = _wire(monkeypatch, grantee=None, existing=None)

    resp = client.post('/api/consents/household', json={'grantee_email': GRANTEE_EMAIL})

    assert resp.status_code == 404
    assert fake_db.commit_count == 0
    assert any(a[0] == 'CONSENT_GRANTED' and a[1] == 'FAILURE' for a, _ in events)


def test_grant_non_household_grantee_returns_404(monkeypatch, client):
    _authenticate(monkeypatch, client)
    fake_db, _, _ = _wire(monkeypatch, _make_grantee(role='ADVISOR'), existing=None)

    resp = client.post('/api/consents/household', json={'grantee_email': GRANTEE_EMAIL})

    assert resp.status_code == 404
    assert fake_db.commit_count == 0


def test_grant_inactive_grantee_returns_404(monkeypatch, client):
    _authenticate(monkeypatch, client)
    fake_db, _, _ = _wire(monkeypatch, _make_grantee(status='PENDING'), existing=None)

    resp = client.post('/api/consents/household', json={'grantee_email': GRANTEE_EMAIL})

    assert resp.status_code == 404
    assert fake_db.commit_count == 0


def test_grant_invalid_email_returns_400(monkeypatch, client):
    _authenticate(monkeypatch, client)
    _wire(monkeypatch, _make_grantee(), existing=None)

    resp = client.post('/api/consents/household', json={'grantee_email': 'not-an-email'})

    assert resp.status_code == 400


def test_grant_missing_email_returns_400(monkeypatch, client):
    _authenticate(monkeypatch, client)
    _wire(monkeypatch, _make_grantee(), existing=None)

    resp = client.post('/api/consents/household', json={})

    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# POST /api/consents/household — access control
# ---------------------------------------------------------------------------

def test_grant_requires_auth(client):
    resp = client.post('/api/consents/household', json={'grantee_email': GRANTEE_EMAIL})
    assert resp.status_code == 401


def test_grant_wrong_role_forbidden(monkeypatch, client):
    _authenticate(monkeypatch, client, role='HOUSEHOLD')  # only INDIVIDUAL may grant

    resp = client.post('/api/consents/household', json={'grantee_email': GRANTEE_EMAIL})

    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# DELETE /api/consents/household/<id> — revoke (soft delete)
# ---------------------------------------------------------------------------

OTHER_GRANTOR_ID = uuid.UUID('99999999-9999-9999-9999-999999999999')


def test_revoke_sets_status_revoked_and_logs(monkeypatch, client):
    _authenticate(monkeypatch, client)
    existing = _make_existing(status='ACTIVE')
    fake_db, events, _ = _wire(monkeypatch, _make_grantee(), existing=existing)

    resp = client.delete(f'/api/consents/household/{CONSENT_ID}')

    assert resp.status_code == 200
    assert resp.get_json()['status'] == 'REVOKED'
    assert existing.status == 'REVOKED'       # soft delete, row kept
    assert fake_db.commit_count == 1
    assert any(a[0] == 'CONSENT_REVOKED' and a[1] == 'SUCCESS' for a, _ in events)


def test_revoke_already_revoked_is_idempotent(monkeypatch, client):
    _authenticate(monkeypatch, client)
    existing = _make_existing(status='REVOKED')
    fake_db, events, _ = _wire(monkeypatch, _make_grantee(), existing=existing)

    resp = client.delete(f'/api/consents/household/{CONSENT_ID}')

    assert resp.status_code == 200
    assert fake_db.commit_count == 0          # no-op, nothing committed
    assert not any(a[0] == 'CONSENT_REVOKED' for a, _ in events)  # no duplicate audit


def test_revoke_foreign_consent_returns_403(monkeypatch, client):
    _authenticate(monkeypatch, client)
    existing = _make_existing(status='ACTIVE')
    existing.grantor_id = OTHER_GRANTOR_ID    # owned by someone else
    fake_db, events, _ = _wire(monkeypatch, _make_grantee(), existing=existing)

    resp = client.delete(f'/api/consents/household/{CONSENT_ID}')

    assert resp.status_code == 403
    assert fake_db.commit_count == 0
    assert not any(a[0] == 'CONSENT_REVOKED' for a, _ in events)


def test_revoke_advisor_consent_returns_404(monkeypatch, client):
    _authenticate(monkeypatch, client)
    existing = _make_existing(access_level='FULL_VIEW', status='ACTIVE')
    fake_db, _, _ = _wire(monkeypatch, _make_grantee(), existing=existing)

    resp = client.delete(f'/api/consents/household/{CONSENT_ID}')

    assert resp.status_code == 404
    assert fake_db.commit_count == 0


def test_revoke_unknown_id_returns_404(monkeypatch, client):
    _authenticate(monkeypatch, client)
    fake_db, _, _ = _wire(monkeypatch, _make_grantee(), existing=None)

    resp = client.delete(f'/api/consents/household/{CONSENT_ID}')

    assert resp.status_code == 404
    assert fake_db.commit_count == 0


def test_revoke_malformed_uuid_returns_404(monkeypatch, client):
    _authenticate(monkeypatch, client)
    _wire(monkeypatch, _make_grantee(), existing=_make_existing())

    resp = client.delete('/api/consents/household/not-a-uuid')

    assert resp.status_code == 404


def test_revoke_requires_auth(client):
    resp = client.delete(f'/api/consents/household/{CONSENT_ID}')
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/household/summary — aggregated, read-only view for household members
# ---------------------------------------------------------------------------

GRANTOR_A = uuid.UUID('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa')
GRANTOR_B = uuid.UUID('bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb')

_FAKE_SUMMARY = {
    'spending_by_category': [{'category': 'Groceries', 'total': '120.00'}],
    'monthly_trend': [{'month': '2026-07', 'spend': '120.00', 'income': '0'}],
}


def _summary_consent(grantor_id, name):
    return SimpleNamespace(
        grantor_id=grantor_id,
        grantor=SimpleNamespace(display_name=name),
    )


def _wire_summary(monkeypatch, consents, valid=True, summary=None):
    """Wire the household summary route: fake consent query + patched services."""
    fake_db = _FakeDbSession()
    events = []
    monkeypatch.setattr(consent_routes, 'db', SimpleNamespace(session=fake_db))
    monkeypatch.setattr(consent_routes, 'Consent', SimpleNamespace(
        query=_Query(consents),
        grantee_id=_Col(), status=_Col(), access_level=_Col(), expires_at=_Col(),
    ))
    monkeypatch.setattr(consent_routes, 'or_', lambda *a, **k: None)
    monkeypatch.setattr(consent_routes, 'log_event', lambda *a, **k: events.append((a, k)))
    monkeypatch.setattr(consent_routes, 'get_valid_consent',
                        lambda gr, ge: (object() if valid else None))
    monkeypatch.setattr(consent_routes, 'household_summary',
                        lambda uid: summary or _FAKE_SUMMARY)
    return fake_db, events


def test_summary_returns_one_entry_per_grantor(monkeypatch, client):
    _authenticate(monkeypatch, client, role='HOUSEHOLD')
    consents = [_summary_consent(GRANTOR_A, 'Alice'), _summary_consent(GRANTOR_B, 'Bob')]
    _, events = _wire_summary(monkeypatch, consents)

    resp = client.get('/api/household/summary')

    assert resp.status_code == 200
    grantors = resp.get_json()['grantors']
    assert len(grantors) == 2
    assert {g['grantor_display_name'] for g in grantors} == {'Alice', 'Bob'}
    assert grantors[0]['spending_by_category'] == _FAKE_SUMMARY['spending_by_category']
    assert grantors[0]['monthly_trend'] == _FAKE_SUMMARY['monthly_trend']
    assert any(a[0] == 'HOUSEHOLD_SUMMARY_ACCESS' for a, _ in events)


def test_summary_empty_when_no_consents(monkeypatch, client):
    _authenticate(monkeypatch, client, role='HOUSEHOLD')
    _wire_summary(monkeypatch, consents=[])

    resp = client.get('/api/household/summary')

    assert resp.status_code == 200
    assert resp.get_json()['grantors'] == []


def test_summary_skips_consent_revoked_midrequest(monkeypatch, client):
    _authenticate(monkeypatch, client, role='HOUSEHOLD')
    consents = [_summary_consent(GRANTOR_A, 'Alice')]
    _wire_summary(monkeypatch, consents, valid=False)  # get_valid_consent -> None

    resp = client.get('/api/household/summary')

    assert resp.status_code == 200
    assert resp.get_json()['grantors'] == []


def test_summary_payload_has_no_sensitive_fields(monkeypatch, client):
    _authenticate(monkeypatch, client, role='HOUSEHOLD')
    _wire_summary(monkeypatch, [_summary_consent(GRANTOR_A, 'Alice')])

    body = client.get('/api/household/summary').get_data(as_text=True)

    for leaked in ('account_number', 'merchant', 'storage_path', 'nric'):
        assert leaked not in body


def test_summary_forbidden_for_non_household_role(monkeypatch, client):
    _authenticate(monkeypatch, client, role='INDIVIDUAL')

    resp = client.get('/api/household/summary')

    assert resp.status_code == 403


def test_summary_requires_auth(client):
    resp = client.get('/api/household/summary')
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# POST /api/consents/advisor — grant FULL_VIEW to an advisor (90-day expiry)
# ---------------------------------------------------------------------------

def test_advisor_grant_creates_consent(monkeypatch, client):
    _authenticate(monkeypatch, client)
    fake_db, events, sent = _wire(monkeypatch, _make_grantee(role='ADVISOR'), existing=None)

    resp = client.post('/api/consents/advisor', json={'grantee_email': GRANTEE_EMAIL})

    assert resp.status_code == 201
    body = resp.get_json()
    assert body['access_level'] == 'FULL_VIEW'
    assert body['status'] == 'ACTIVE'
    assert len(fake_db.added) == 1
    # 90-day expiry set on the new row
    created = fake_db.added[0]
    assert created.expires_at is not None
    assert created.expires_at > datetime.utcnow() + timedelta(days=89)
    assert fake_db.commit_count == 1
    assert any(a[0] == 'CONSENT_GRANTED' and a[1] == 'SUCCESS' for a, _ in events)
    assert len(sent) == 1


def test_advisor_grant_reactivates_with_fresh_expiry(monkeypatch, client):
    _authenticate(monkeypatch, client)
    existing = _make_existing(access_level='FULL_VIEW', status='REVOKED')  # expires_at=None
    fake_db, events, _ = _wire(monkeypatch, _make_grantee(role='ADVISOR'), existing=existing)

    resp = client.post('/api/consents/advisor', json={'grantee_email': GRANTEE_EMAIL})

    assert resp.status_code == 201
    assert existing.status == 'ACTIVE'
    assert existing.expires_at is not None                     # fresh 90-day clock
    assert existing.expires_at > datetime.utcnow() + timedelta(days=89)
    assert fake_db.added == []
    assert fake_db.commit_count == 1


def test_advisor_grant_non_advisor_returns_404(monkeypatch, client):
    _authenticate(monkeypatch, client)
    fake_db, _, _ = _wire(monkeypatch, _make_grantee(role='HOUSEHOLD'), existing=None)

    resp = client.post('/api/consents/advisor', json={'grantee_email': GRANTEE_EMAIL})

    assert resp.status_code == 404
    assert fake_db.commit_count == 0


def test_advisor_grant_conflicting_household_consent_returns_409(monkeypatch, client):
    _authenticate(monkeypatch, client)
    existing = _make_existing(access_level='SUMMARY_ONLY', status='ACTIVE')
    fake_db, events, _ = _wire(monkeypatch, _make_grantee(role='ADVISOR'), existing=existing)

    resp = client.post('/api/consents/advisor', json={'grantee_email': GRANTEE_EMAIL})

    assert resp.status_code == 409
    assert fake_db.commit_count == 0
    assert any(a[0] == 'CONSENT_GRANTED' and a[1] == 'FAILURE' for a, _ in events)


def test_advisor_grant_to_self_returns_400(monkeypatch, client):
    _authenticate(monkeypatch, client)
    fake_db, _, _ = _wire(monkeypatch, _make_grantee(role='ADVISOR'), existing=None)

    resp = client.post('/api/consents/advisor', json={'grantee_email': GRANTOR_EMAIL})

    assert resp.status_code == 400
    assert fake_db.commit_count == 0


def test_advisor_grant_wrong_role_forbidden(monkeypatch, client):
    _authenticate(monkeypatch, client, role='ADVISOR')  # only INDIVIDUAL may grant

    resp = client.post('/api/consents/advisor', json={'grantee_email': GRANTEE_EMAIL})

    assert resp.status_code == 403


def test_advisor_grant_requires_auth(client):
    resp = client.post('/api/consents/advisor', json={'grantee_email': GRANTEE_EMAIL})
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# DELETE /api/consents/advisor/<id> — revoke advisor access (soft delete)
# ---------------------------------------------------------------------------

def test_advisor_revoke_sets_status_revoked_and_logs(monkeypatch, client):
    _authenticate(monkeypatch, client)
    existing = _make_existing(access_level='FULL_VIEW', status='ACTIVE')
    fake_db, events, _ = _wire(monkeypatch, _make_grantee(role='ADVISOR'), existing=existing)

    resp = client.delete(f'/api/consents/advisor/{CONSENT_ID}')

    assert resp.status_code == 200
    assert resp.get_json()['status'] == 'REVOKED'
    assert existing.status == 'REVOKED'
    assert fake_db.commit_count == 1
    assert any(a[0] == 'CONSENT_REVOKED' and a[1] == 'SUCCESS' for a, _ in events)


def test_advisor_revoke_already_revoked_is_idempotent(monkeypatch, client):
    _authenticate(monkeypatch, client)
    existing = _make_existing(access_level='FULL_VIEW', status='REVOKED')
    fake_db, events, _ = _wire(monkeypatch, _make_grantee(role='ADVISOR'), existing=existing)

    resp = client.delete(f'/api/consents/advisor/{CONSENT_ID}')

    assert resp.status_code == 200
    assert fake_db.commit_count == 0
    assert not any(a[0] == 'CONSENT_REVOKED' for a, _ in events)


def test_advisor_revoke_foreign_consent_returns_403(monkeypatch, client):
    _authenticate(monkeypatch, client)
    existing = _make_existing(access_level='FULL_VIEW', status='ACTIVE')
    existing.grantor_id = OTHER_GRANTOR_ID
    fake_db, events, _ = _wire(monkeypatch, _make_grantee(role='ADVISOR'), existing=existing)

    resp = client.delete(f'/api/consents/advisor/{CONSENT_ID}')

    assert resp.status_code == 403
    assert fake_db.commit_count == 0
    assert not any(a[0] == 'CONSENT_REVOKED' for a, _ in events)


def test_advisor_revoke_household_consent_returns_404(monkeypatch, client):
    _authenticate(monkeypatch, client)
    existing = _make_existing(access_level='SUMMARY_ONLY', status='ACTIVE')
    fake_db, _, _ = _wire(monkeypatch, _make_grantee(role='ADVISOR'), existing=existing)

    resp = client.delete(f'/api/consents/advisor/{CONSENT_ID}')

    assert resp.status_code == 404
    assert fake_db.commit_count == 0


def test_advisor_revoke_unknown_id_returns_404(monkeypatch, client):
    _authenticate(monkeypatch, client)
    fake_db, _, _ = _wire(monkeypatch, _make_grantee(role='ADVISOR'), existing=None)

    resp = client.delete(f'/api/consents/advisor/{CONSENT_ID}')

    assert resp.status_code == 404
    assert fake_db.commit_count == 0


def test_advisor_revoke_malformed_uuid_returns_404(monkeypatch, client):
    _authenticate(monkeypatch, client)
    _wire(monkeypatch, _make_grantee(role='ADVISOR'), existing=_make_existing(access_level='FULL_VIEW'))

    resp = client.delete('/api/consents/advisor/not-a-uuid')

    assert resp.status_code == 404


def test_advisor_revoke_requires_auth(client):
    resp = client.delete(f'/api/consents/advisor/{CONSENT_ID}')
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/advisor/clients — advisor lists their FULL_VIEW clients
# ---------------------------------------------------------------------------

def test_advisor_clients_lists_grantors(monkeypatch, client):
    _authenticate(monkeypatch, client, role='ADVISOR')
    consents = [_summary_consent(GRANTOR_A, 'Alice'), _summary_consent(GRANTOR_B, 'Bob')]
    _wire_summary(monkeypatch, consents)

    resp = client.get('/api/advisor/clients')

    assert resp.status_code == 200
    clients = resp.get_json()['clients']
    assert {c['display_name'] for c in clients} == {'Alice', 'Bob'}
    assert {c['grantor_id'] for c in clients} == {str(GRANTOR_A), str(GRANTOR_B)}


def test_advisor_clients_empty(monkeypatch, client):
    _authenticate(monkeypatch, client, role='ADVISOR')
    _wire_summary(monkeypatch, consents=[])

    resp = client.get('/api/advisor/clients')

    assert resp.status_code == 200
    assert resp.get_json()['clients'] == []


def test_advisor_clients_payload_has_no_sensitive_fields(monkeypatch, client):
    _authenticate(monkeypatch, client, role='ADVISOR')
    _wire_summary(monkeypatch, [_summary_consent(GRANTOR_A, 'Alice')])

    body = client.get('/api/advisor/clients').get_data(as_text=True)

    for leaked in ('email', 'account_number', 'spending', 'total', 'nric'):
        assert leaked not in body


def test_advisor_clients_forbidden_for_non_advisor(monkeypatch, client):
    _authenticate(monkeypatch, client, role='INDIVIDUAL')

    resp = client.get('/api/advisor/clients')

    assert resp.status_code == 403


def test_advisor_clients_requires_auth(client):
    resp = client.get('/api/advisor/clients')
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/advisor/clients/<grantor_id>/analytics — consent-gated full view
# ---------------------------------------------------------------------------

_FAKE_FULL = {
    'month': '2026-07',
    'spending_by_category': [{'category': 'Groceries', 'total': '120.00'}],
    'monthly_trend': [{'month': '2026-07', 'spend': '120.00', 'income': '0'}],
    'top_merchants': [{'merchant': 'Cold Storage', 'total': '80.00'}],
}


def _valid_consent(level='FULL_VIEW', name='Alice'):
    return SimpleNamespace(access_level=level, grantor=SimpleNamespace(display_name=name))


def _wire_analytics(monkeypatch, consent, analytics=None):
    events = []
    monkeypatch.setattr(consent_routes, 'log_event', lambda *a, **k: events.append((a, k)))
    monkeypatch.setattr(consent_routes, 'get_valid_consent', lambda gr, ge: consent)
    monkeypatch.setattr(consent_routes, 'full_analytics', lambda uid: analytics or _FAKE_FULL)
    return events


def test_advisor_analytics_returns_full_data(monkeypatch, client):
    _authenticate(monkeypatch, client, role='ADVISOR')
    events = _wire_analytics(monkeypatch, _valid_consent())

    resp = client.get(f'/api/advisor/clients/{GRANTOR_A}/analytics')

    assert resp.status_code == 200
    body = resp.get_json()
    assert body['grantor_id'] == str(GRANTOR_A)
    assert body['display_name'] == 'Alice'
    assert set(body['analytics']) >= {'spending_by_category', 'monthly_trend', 'top_merchants'}
    assert body['analytics']['top_merchants'] == _FAKE_FULL['top_merchants']
    assert any(a[0] == 'ADVISOR_DATA_ACCESS' and a[1] == 'SUCCESS' for a, _ in events)


def test_advisor_analytics_no_consent_returns_403(monkeypatch, client):
    _authenticate(monkeypatch, client, role='ADVISOR')
    events = _wire_analytics(monkeypatch, consent=None)

    resp = client.get(f'/api/advisor/clients/{GRANTOR_A}/analytics')

    assert resp.status_code == 403
    assert not any(a[0] == 'ADVISOR_DATA_ACCESS' for a, _ in events)


def test_advisor_analytics_non_full_view_consent_returns_403(monkeypatch, client):
    _authenticate(monkeypatch, client, role='ADVISOR')
    events = _wire_analytics(monkeypatch, _valid_consent(level='SUMMARY_ONLY'))

    resp = client.get(f'/api/advisor/clients/{GRANTOR_A}/analytics')

    assert resp.status_code == 403
    assert not any(a[0] == 'ADVISOR_DATA_ACCESS' for a, _ in events)


def test_advisor_analytics_malformed_grantor_id_returns_403(monkeypatch, client):
    _authenticate(monkeypatch, client, role='ADVISOR')
    _wire_analytics(monkeypatch, _valid_consent())

    resp = client.get('/api/advisor/clients/not-a-uuid/analytics')

    assert resp.status_code == 403


def test_advisor_analytics_forbidden_for_non_advisor(monkeypatch, client):
    _authenticate(monkeypatch, client, role='INDIVIDUAL')

    resp = client.get(f'/api/advisor/clients/{GRANTOR_A}/analytics')

    assert resp.status_code == 403


def test_advisor_analytics_requires_auth(client):
    resp = client.get(f'/api/advisor/clients/{GRANTOR_A}/analytics')
    assert resp.status_code == 401
