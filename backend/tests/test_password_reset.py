from __future__ import annotations

import hashlib
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from app import create_app
from app.routes import auth as auth_routes
from app.utils.crypto import hash_password, verify_password


class _Query:
    """Small fake SQLAlchemy-style query object for route unit tests."""

    def __init__(self, result):
        self.result = result
        self.filter_calls = []

    def filter_by(self, **kwargs):
        self.filter_calls.append(kwargs)
        return self

    def first(self):
        return self.result


class _DeleteQuery:
    """Fake query object used for invalidating all sessions."""

    def __init__(self):
        self.filter_calls = []
        self.delete_called = False

    def filter_by(self, **kwargs):
        self.filter_calls.append(kwargs)
        return self

    def delete(self):
        self.delete_called = True
        return 1


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


@pytest.fixture
def client():
    app = create_app("development")
    app.config.update(TESTING=True)
    return app.test_client()


def test_register_stores_only_token_hash_and_emails_raw_token(monkeypatch, client):
    password = "Ocean!Lantern92-Maple"
    fake_db_session = _FakeDbSession()
    sent_email = {}

    class FakeUser:
        query = _Query(None)

        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)
            self.id = "user-1"
            self.roles = []

    class FakeRole:
        query = _Query(SimpleNamespace(id=1))

    def capture_email(to_email, display_name, raw_token):
        sent_email["to_email"] = to_email
        sent_email["display_name"] = display_name
        sent_email["raw_token"] = raw_token

    monkeypatch.setattr(auth_routes, "User", FakeUser)
    monkeypatch.setattr(auth_routes, "Role", FakeRole)
    monkeypatch.setattr(
        auth_routes,
        "db",
        SimpleNamespace(session=fake_db_session),
    )
    monkeypatch.setattr(auth_routes, "send_verification_email", capture_email)
    monkeypatch.setattr(auth_routes, "log_event", lambda *args, **kwargs: None)

    before = datetime.utcnow()
    response = client.post(
        "/api/auth/register",
        json={
            "email": "newuser@example.com",
            "display_name": "New User",
            "password": password,
        },
    )
    after = datetime.utcnow()

    assert response.status_code == 201
    assert len(fake_db_session.added) == 1

    created_user = fake_db_session.added[0]
    raw_token = sent_email["raw_token"]
    expected_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

    assert sent_email["to_email"] == "newuser@example.com"
    assert created_user.email_verification_token_hash == expected_hash
    assert created_user.email_verification_token_hash != raw_token
    assert verify_password(password, created_user.password_hash) is True

    expiry_seconds = (
        created_user.email_verification_expires_at - before
    ).total_seconds()
    assert 86399 <= expiry_seconds <= 86401
    assert created_user.email_verification_expires_at <= (
        after + timedelta(hours=24, seconds=1)
    )


def test_reset_request_stores_hash_sends_raw_token_and_sets_15_min_expiry(
    monkeypatch,
    client,
):
    fake_db_session = _FakeDbSession()
    sent_email = {}

    user = SimpleNamespace(
        id="user-2",
        email="active@example.com",
        display_name="Active User",
        status="ACTIVE",
    )

    class FakeResetToken:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    def capture_email(to_email, display_name, raw_token):
        sent_email["to_email"] = to_email
        sent_email["display_name"] = display_name
        sent_email["raw_token"] = raw_token

    monkeypatch.setattr(
        auth_routes,
        "User",
        SimpleNamespace(query=_Query(user)),
    )
    monkeypatch.setattr(auth_routes, "PasswordResetToken", FakeResetToken)
    monkeypatch.setattr(
        auth_routes,
        "db",
        SimpleNamespace(session=fake_db_session),
    )
    monkeypatch.setattr(auth_routes, "send_password_reset_email", capture_email)
    monkeypatch.setattr(auth_routes, "log_event", lambda *args, **kwargs: None)

    before = datetime.utcnow()
    response = client.post(
        "/api/auth/password-reset/request",
        json={"email": "active@example.com"},
    )

    assert response.status_code == 200
    assert len(fake_db_session.added) == 1

    reset_token = fake_db_session.added[0]
    raw_token = sent_email["raw_token"]
    expected_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

    assert sent_email["to_email"] == user.email
    assert reset_token.token_hash == expected_hash
    assert reset_token.token_hash != raw_token

    expiry_seconds = (reset_token.expires_at - before).total_seconds()
    assert 899 <= expiry_seconds <= 901


def test_reset_confirm_changes_password_marks_token_used_and_clears_sessions(
    monkeypatch,
    client,
):
    old_password = "OldPassword!123"
    new_password = "Ocean!Lantern92-Maple"
    raw_token = "valid-reset-token"

    user = SimpleNamespace(
        id="user-3",
        password_hash=hash_password(old_password),
    )
    reset_token = SimpleNamespace(
        user=user,
        token_hash=hashlib.sha256(raw_token.encode("utf-8")).hexdigest(),
        expires_at=datetime.utcnow() + timedelta(minutes=15),
        used_at=None,
    )

    reset_query = _Query(reset_token)
    session_query = _DeleteQuery()
    fake_db_session = _FakeDbSession()

    monkeypatch.setattr(
        auth_routes,
        "PasswordResetToken",
        SimpleNamespace(query=reset_query),
    )
    monkeypatch.setattr(
        auth_routes,
        "Session",
        SimpleNamespace(query=session_query),
    )
    monkeypatch.setattr(
        auth_routes,
        "db",
        SimpleNamespace(session=fake_db_session),
    )
    monkeypatch.setattr(auth_routes, "log_event", lambda *args, **kwargs: None)

    response = client.post(
        "/api/auth/password-reset/confirm",
        json={"token": raw_token, "new_password": new_password},
    )

    assert response.status_code == 200
    assert reset_query.filter_calls == [
        {
            "token_hash": hashlib.sha256(
                raw_token.encode("utf-8")
            ).hexdigest()
        }
    ]
    assert reset_token.used_at is not None
    assert verify_password(old_password, user.password_hash) is False
    assert verify_password(new_password, user.password_hash) is True
    assert session_query.filter_calls == [{"user_id": user.id}]
    assert session_query.delete_called is True


def test_reset_confirm_rejects_used_token(monkeypatch, client):
    old_password = "OldPassword!123"
    raw_token = "already-used-token"

    user = SimpleNamespace(
        id="user-4",
        password_hash=hash_password(old_password),
    )

    original_hash = user.password_hash

    reset_token = SimpleNamespace(
        user=user,
        expires_at=datetime.utcnow() + timedelta(minutes=15),
        used_at=datetime.utcnow(),
    )

    fake_db_session = _FakeDbSession()

    monkeypatch.setattr(
        auth_routes,
        "PasswordResetToken",
        SimpleNamespace(query=_Query(reset_token)),
    )
    monkeypatch.setattr(
        auth_routes,
        "db",
        SimpleNamespace(session=fake_db_session),
    )
    monkeypatch.setattr(auth_routes, "log_event", lambda *args, **kwargs: None)

    response = client.post(
        "/api/auth/password-reset/confirm",
        json={
            "token": raw_token,
            "new_password": "Ocean!Lantern92-Maple",
        },
    )

    assert response.status_code == 400
    assert user.password_hash == original_hash
    assert fake_db_session.commit_count == 0


def test_reset_confirm_rejects_expired_token(monkeypatch, client):
    old_password = "OldPassword!123"
    raw_token = "expired-reset-token"

    user = SimpleNamespace(
        id="user-5",
        password_hash=hash_password(old_password),
    )
    original_hash = user.password_hash

    reset_token = SimpleNamespace(
        user=user,
        expires_at=datetime.utcnow() - timedelta(seconds=1),
        used_at=None,
    )

    fake_db_session = _FakeDbSession()

    monkeypatch.setattr(
        auth_routes,
        "PasswordResetToken",
        SimpleNamespace(query=_Query(reset_token)),
    )
    monkeypatch.setattr(
        auth_routes,
        "db",
        SimpleNamespace(session=fake_db_session),
    )
    monkeypatch.setattr(auth_routes, "log_event", lambda *args, **kwargs: None)

    response = client.post(
        "/api/auth/password-reset/confirm",
        json={
            "token": raw_token,
            "new_password": "Ocean!Lantern92-Maple",
        },
    )

    assert response.status_code == 400
    assert user.password_hash == original_hash
    assert fake_db_session.commit_count == 0