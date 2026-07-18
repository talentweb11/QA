from __future__ import annotations

from flask import Blueprint, current_app, g, jsonify, request

from app.extensions import db
from app.middleware.auth import require_auth
from app.models import Session
from app.services.audit import log_event
from app.utils.crypto import (
    hash_password,
    validate_password_complexity,
    verify_password,
)
from app.utils.request_meta import client_ip, user_agent

users_bp = Blueprint('users', __name__, url_prefix='/api/users')

# FR-03: GET    /api/users/me
# FR-04: PATCH  /api/users/me
# FR-04: PATCH  /api/users/me/password
# FR-05: DELETE /api/users/me


# ---------------------------------------------------------------------------
# FR-03: Get own profile
# ---------------------------------------------------------------------------

@users_bp.get('/me')
@require_auth
def get_profile():
    user = g.current_user
    return jsonify({
        'id': str(user.id),
        'email': user.email,
        'display_name': user.display_name,
        'roles': sorted(user.role_names),
        'mfa_enabled': user.mfa_enabled,
        'status': user.status,
        'created_at': user.created_at.isoformat(),
    }), 200


# ---------------------------------------------------------------------------
# FR-04: Update display name
# ---------------------------------------------------------------------------

@users_bp.patch('/me')
@require_auth
def update_profile():
    data = request.get_json(silent=True) or {}
    display_name = (data.get('display_name') or '').strip()

    if not display_name:
        return jsonify({'error': 'display_name must be a non-empty string'}), 400
    if len(display_name) > 100:
        return jsonify({'error': 'display_name must be 100 characters or fewer'}), 400

    user = g.current_user
    user.display_name = display_name
    db.session.commit()

    log_event('PROFILE_UPDATED', 'SUCCESS', client_ip(), user_id=user.id, user_agent=user_agent())
    return jsonify({
        'id': str(user.id),
        'email': user.email,
        'display_name': user.display_name,
        'roles': sorted(user.role_names),
        'mfa_enabled': user.mfa_enabled,
        'status': user.status,
        'created_at': user.created_at.isoformat(),
    }), 200


# ---------------------------------------------------------------------------
# FR-04 / SR-10: Change password
# ---------------------------------------------------------------------------

@users_bp.patch('/me/password')
@require_auth
def change_password():
    data = request.get_json(silent=True) or {}
    current_password = data.get('current_password') or ''
    new_password = data.get('new_password') or ''
    ip, ua = client_ip(), user_agent()
    user = g.current_user

    if not current_password or not new_password:
        return jsonify({'error': 'current_password and new_password are required'}), 400

    if not verify_password(current_password, user.password_hash):
        log_event('PASSWORD_CHANGE_FAILED', 'FAILURE', ip, user_id=user.id, user_agent=ua)
        return jsonify({'error': 'Current password is incorrect'}), 401

    valid, reason = validate_password_complexity(new_password)
    if not valid:
        return jsonify({'error': reason}), 400

    user.password_hash = hash_password(new_password)

    # Invalidate all sessions except the current one
    Session.query.filter(
        Session.user_id == user.id,
        Session.id != g.session.id,
    ).delete()
    db.session.commit()

    log_event('PASSWORD_CHANGED', 'SUCCESS', ip, user_id=user.id, user_agent=ua)
    return jsonify({'message': 'Password updated successfully'}), 200


# ---------------------------------------------------------------------------
# FR-05: Delete account
# ---------------------------------------------------------------------------

@users_bp.delete('/me')
@require_auth
def delete_account():
    data = request.get_json(silent=True) or {}
    password = data.get('password') or ''
    ip, ua = client_ip(), user_agent()
    user = g.current_user

    if not password:
        return jsonify({'error': 'password is required to confirm account deletion'}), 400

    if not verify_password(password, user.password_hash):
        log_event('ACCOUNT_DELETE_FAILED', 'FAILURE', ip, user_id=user.id, user_agent=ua)
        return jsonify({'error': 'Incorrect password'}), 401

    # Audit log written before deletion — cascade will remove all user data
    log_event('ACCOUNT_DELETED', 'SUCCESS', ip, user_id=user.id, user_agent=ua)

    db.session.delete(user)
    db.session.commit()

    return jsonify({'message': 'Account deleted'}), 200
