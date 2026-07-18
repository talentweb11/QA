from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from app import create_app
from app.middleware import auth as auth_mw
from app.routes import auth as auth_routes
from app.routes import consents as consent_routes
from app.utils.crypto import verify_password


GRANTOR_ID = uuid.UUID('11111111-1111-1111-1111-111111111111')
GRANTOR_EMAIL = 'grantor@example.com'
GRANTEE_EMAIL = 'member@example.com'


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

class _Query:
    def __init__(self, result):
        self.result = result

    def filter_by(self, **kw):
        return self

    def filter(self, *a):
        return self

    def first(self):
        return self.result

    def all(self):
        return self.result if isinstance(self.result, list) else []


class _RoleQuery:
    """Returns a distinct role object per requested role_name."""

    def filter_by(self, role_name=None, **kw):
        self._name = role_name
        return self

    def first(self):
        return SimpleNamespace(id=abs(hash(self._name)) % 1000, role_name=self._name)


class _FakeDbSession:
    def __init__(self):
        self.added = []
        self.commits = 0
        self.flushes = 0

    def add(self, item):
        self.added.append(item)

    def flush(self):
        self.flushes += 1

    def commit(self):
        self.commits += 1

    def rollback(self):
        pass


class _SessionQuery:
    def __init__(self, session):
        self.session = session

    def filter_by(self, **kw):
        return self

    def first(self):
        return self.session


@pytest.fixture
def client():
    app = create_app('development')
    app.config.update(TESTING=True)
    return app.test_client()


def _authenticate(monkeypatch, client, *, role='INDIVIDUAL'):
    user = SimpleNamespace(
        id=GRANTOR_ID, email=GRANTOR_EMAIL, display_name='Ivy Individual',
        role_names={role},
    )
    session = SimpleNamespace(
        id='sess-1', user=user,
        expires_at=datetime.utcnow() + timedelta(hours=1),
        last_active=datetime.utcnow(),
    )
    monkeypatch.setattr(auth_mw, 'Session', SimpleNamespace(query=_SessionQuery(session)))
    monkeypatch.setattr(auth_mw, 'db', SimpleNamespace(session=SimpleNamespace(
        commit=lambda: None, delete=lambda *a: None, rollback=lambda: None,
    )))
    client.set_cookie('session_token', 'test-token')
    return user


def _make_user_model(query_result):
    created = []

    class FakeUser:
        query = _Query(query_result)

        def __init__(self, **kw):
            self.__dict__.update(kw)
            self.id = uuid.uuid4()
            self.roles = []
            created.append(self)

        def has_role(self, name):
            return any(getattr(r, 'role_name', None) == name for r in self.roles)

    return FakeUser, created


def _make_consent_model(query_result):
    added = []

    class FakeConsent:
        query = _Query(query_result)

        def __init__(self, **kw):
            self.__dict__.update(kw)
            self.id = uuid.uuid4()
            added.append(self)

    return FakeConsent, added


def _existing_active_user():
    u = SimpleNamespace(
        id=uuid.uuid4(), email=GRANTEE_EMAIL, display_name='Hank',
        status='ACTIVE', roles=[],
    )
    u.has_role = lambda name: any(getattr(r, 'role_name', None) == name for r in u.roles)
    return u


def _wire_invite(monkeypatch, *, user_query_result, consent_query_result=None):
    fake_db = _FakeDbSession()
    events, invites, notifs = [], [], []
    UserModel, created = _make_user_model(user_query_result)
    ConsentModel, added = _make_consent_model(consent_query_result)
    monkeypatch.setattr(consent_routes, 'db', SimpleNamespace(session=fake_db))
    monkeypatch.setattr(consent_routes, 'User', UserModel)
    monkeypatch.setattr(consent_routes, 'Consent', ConsentModel)
    monkeypatch.setattr(consent_routes, 'Role', SimpleNamespace(query=_RoleQuery()))
    monkeypatch.setattr(consent_routes, 'log_event', lambda *a, **k: events.append((a, k)))
    monkeypatch.setattr(consent_routes, 'send_invitation',
                        lambda *a, **k: invites.append((a, k)))
    monkeypatch.setattr(consent_routes, 'send_consent_notification',
                        lambda *a, **k: notifs.append((a, k)))
    return SimpleNamespace(db=fake_db, events=events, invites=invites,
                           notifs=notifs, created=created, added=added)


# ---------------------------------------------------------------------------
# POST /api/consents/household/invite
# ---------------------------------------------------------------------------

def test_invite_new_person_creates_pending_account_and_sends_link(monkeypatch, client):
    _authenticate(monkeypatch, client)
    w = _wire_invite(monkeypatch, user_query_result=None, consent_query_result=None)

    resp = client.post('/api/consents/household/invite', json={'grantee_email': GRANTEE_EMAIL})

    assert resp.status_code == 201
    assert resp.get_json()['status'] == 'INVITED'
    assert len(w.created) == 1
    new_user = w.created[0]
    assert new_user.status == 'PENDING'
    assert {r.role_name for r in new_user.roles} == {'INDIVIDUAL', 'HOUSEHOLD'}
    assert new_user.email_verification_token_hash               # invite token stored
    assert len(w.added) == 1                                    # consent row created
    assert len(w.invites) == 1                                  # invitation emailed
    assert len(w.notifs) == 0
    assert w.db.commits == 1


def test_invite_existing_active_user_adds_household_and_shares(monkeypatch, client):
    _authenticate(monkeypatch, client)
    existing = _existing_active_user()
    w = _wire_invite(monkeypatch, user_query_result=existing, consent_query_result=None)

    resp = client.post('/api/consents/household/invite', json={'grantee_email': GRANTEE_EMAIL})

    assert resp.status_code == 201
    assert resp.get_json()['status'] == 'SHARED'
    assert existing.has_role('HOUSEHOLD')      # role added to existing account
    assert len(w.added) == 1                   # consent created
    assert len(w.notifs) == 1                  # notified (not an invite link)
    assert len(w.invites) == 0
    assert len(w.created) == 0                  # no new account created


def test_invite_self_returns_400(monkeypatch, client):
    _authenticate(monkeypatch, client)
    w = _wire_invite(monkeypatch, user_query_result=None)

    resp = client.post('/api/consents/household/invite', json={'grantee_email': GRANTOR_EMAIL})

    assert resp.status_code == 400
    assert w.db.commits == 0
    assert len(w.created) == 0


def test_invite_invalid_email_returns_400(monkeypatch, client):
    _authenticate(monkeypatch, client)
    _wire_invite(monkeypatch, user_query_result=None)

    resp = client.post('/api/consents/household/invite', json={'grantee_email': 'not-an-email'})

    assert resp.status_code == 400


def test_invite_requires_individual(monkeypatch, client):
    _authenticate(monkeypatch, client, role='HOUSEHOLD')
    _wire_invite(monkeypatch, user_query_result=None)

    resp = client.post('/api/consents/household/invite', json={'grantee_email': GRANTEE_EMAIL})

    assert resp.status_code == 403


def test_invite_requires_auth(client):
    resp = client.post('/api/consents/household/invite', json={'grantee_email': GRANTEE_EMAIL})
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# POST /api/consents/advisor/invite
# ---------------------------------------------------------------------------

def test_invite_advisor_new_person_grants_full_view_with_expiry(monkeypatch, client):
    _authenticate(monkeypatch, client)
    w = _wire_invite(monkeypatch, user_query_result=None, consent_query_result=None)

    resp = client.post('/api/consents/advisor/invite', json={'grantee_email': GRANTEE_EMAIL})

    assert resp.status_code == 201
    assert resp.get_json()['status'] == 'INVITED'
    new_user = w.created[0]
    assert {r.role_name for r in new_user.roles} == {'INDIVIDUAL', 'ADVISOR'}
    consent = w.added[0]
    assert consent.access_level == 'FULL_VIEW'
    assert consent.expires_at is not None            # 90-day advisor expiry
    assert w.invites[0][0][3] == 'FULL_VIEW'          # invite email carried the level


def test_invite_advisor_existing_active_user_adds_advisor_and_shares(monkeypatch, client):
    _authenticate(monkeypatch, client)
    existing = _existing_active_user()
    w = _wire_invite(monkeypatch, user_query_result=existing, consent_query_result=None)

    resp = client.post('/api/consents/advisor/invite', json={'grantee_email': GRANTEE_EMAIL})

    assert resp.status_code == 201
    assert resp.get_json()['status'] == 'SHARED'
    assert existing.has_role('ADVISOR')
    assert w.added[0].access_level == 'FULL_VIEW'
    assert len(w.notifs) == 1
    assert len(w.invites) == 0


# ---------------------------------------------------------------------------
# POST /api/auth/accept-invite
# ---------------------------------------------------------------------------

def _wire_accept(monkeypatch, user):
    fake_db = _FakeDbSession()
    events = []
    monkeypatch.setattr(auth_routes, 'User', SimpleNamespace(query=_Query(user)))
    monkeypatch.setattr(auth_routes, 'Role', SimpleNamespace(query=_RoleQuery()))
    monkeypatch.setattr(auth_routes, 'db', SimpleNamespace(session=fake_db))
    monkeypatch.setattr(auth_routes, 'log_event', lambda *a, **k: events.append((a, k)))
    return fake_db, events


def _pending_invitee(expires_delta=timedelta(days=1)):
    # Specialized role (HOUSEHOLD here) was assigned when the invite was created;
    # accept-invite should preserve it and add only the INDIVIDUAL base role.
    u = SimpleNamespace(
        id=uuid.uuid4(), email=GRANTEE_EMAIL, display_name='member',
        status='PENDING', roles=[SimpleNamespace(role_name='HOUSEHOLD')],
        password_hash='unusable',
        email_verification_token_hash=hashlib.sha256(b'the-token').hexdigest(),
        email_verification_expires_at=datetime.utcnow() + expires_delta,
    )
    u.has_role = lambda name: any(getattr(r, 'role_name', None) == name for r in u.roles)
    return u


def test_accept_invite_activates_account(monkeypatch, client):
    user = _pending_invitee()
    fake_db, _ = _wire_accept(monkeypatch, user)

    resp = client.post('/api/auth/accept-invite', json={
        'token': 'the-token',
        'password': 'Ocean!Lantern92-Maple',
        'display_name': 'New Member',
    })

    assert resp.status_code == 200
    assert user.status == 'ACTIVE'
    assert user.display_name == 'New Member'
    assert user.email_verification_token_hash is None
    assert verify_password('Ocean!Lantern92-Maple', user.password_hash) is True
    assert {r.role_name for r in user.roles} == {'INDIVIDUAL', 'HOUSEHOLD'}
    assert fake_db.commits == 1


def test_accept_invite_expired_returns_400(monkeypatch, client):
    user = _pending_invitee(expires_delta=timedelta(seconds=-1))
    fake_db, _ = _wire_accept(monkeypatch, user)

    resp = client.post('/api/auth/accept-invite', json={
        'token': 'the-token', 'password': 'Ocean!Lantern92-Maple', 'display_name': 'X',
    })

    assert resp.status_code == 400
    assert user.status == 'PENDING'
    assert fake_db.commits == 0


def test_accept_invite_weak_password_returns_400(monkeypatch, client):
    user = _pending_invitee()
    fake_db, _ = _wire_accept(monkeypatch, user)

    resp = client.post('/api/auth/accept-invite', json={
        'token': 'the-token', 'password': 'short', 'display_name': 'X',
    })

    assert resp.status_code == 400
    assert fake_db.commits == 0
