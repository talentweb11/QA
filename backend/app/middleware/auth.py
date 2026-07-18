from __future__ import annotations

import hashlib
from datetime import datetime, timedelta
from functools import wraps

from flask import abort, g, jsonify, request

from app.extensions import db
from app.models import Session

_IDLE_TIMEOUT_MINUTES = 15


def require_auth(f):
    """Validate session cookie, enforce idle timeout, and bind g.current_user + g.session."""
    @wraps(f)
    def decorated(*args, **kwargs):
        raw_token = request.cookies.get('session_token')
        if not raw_token:
            return jsonify({'error': 'Authentication required'}), 401

        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        session = Session.query.filter_by(token_hash=token_hash).first()

        if not session:
            return jsonify({'error': 'Invalid or expired session'}), 401

        now = datetime.utcnow()

        if session.expires_at < now:
            db.session.delete(session)
            db.session.commit()
            return jsonify({'error': 'Session expired'}), 401

        if now - session.last_active > timedelta(minutes=_IDLE_TIMEOUT_MINUTES):
            db.session.delete(session)
            db.session.commit()
            return jsonify({'error': 'Session timed out due to inactivity'}), 401

        session.last_active = now
        db.session.commit()

        g.current_user = session.user
        g.session = session
        return f(*args, **kwargs)

    return decorated


def require_role(*roles: str):
    """Stack on top of @require_auth. Returns 403 unless g.current_user holds at
    least one of `roles` (a user may hold several)."""
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if not set(roles) & g.current_user.role_names:
                return jsonify({'error': 'Forbidden'}), 403
            return f(*args, **kwargs)

        return decorated

    return decorator


def assert_owns_resource(record_user_id) -> None:
    """Abort with 403 unless `record_user_id` belongs to the current user.

    Call this inside a route before returning or modifying a user-owned record
    that was looked up by a means other than filtering the query by user_id
    (e.g. a record fetched by its own primary key). For records fetched via a
    query already filtered by user_id, that filter is the ownership check —
    this helper is redundant there.
    """
    if str(record_user_id) != str(g.current_user.id):
        abort(403, description='Forbidden')
