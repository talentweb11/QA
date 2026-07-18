from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from flask import Blueprint, g, jsonify, request

from app.extensions import db
from app.middleware.auth import require_auth, require_role
from app.models import AuditLog, Role, User
from app.services.audit import log_event
from app.utils.request_meta import client_ip, user_agent

admin_bp = Blueprint('admin', __name__, url_prefix='/api/admin')

# FR-11: GET    /api/admin/users
# FR-11: PATCH  /api/admin/users/:id/status
# FR-11: DELETE /api/admin/users/:id
# FR-11: PATCH  /api/admin/users/:id/role
# SR-16: GET    /api/admin/audit-logs

_VALID_STATUSES = {'ACTIVE', 'SUSPENDED'}
_VALID_OUTCOMES = {'SUCCESS', 'FAILURE'}
_DEFAULT_PAGE_SIZE = 50
_MAX_PAGE_SIZE = 100


def _serialize_user(user: User) -> dict:
    """SR-15 allowlist — the only fields an admin response may ever include.

    Deliberately excludes: password_hash, totp_secret, nric,
    account_number_encrypted, email_verification_token_hash.
    """
    return {
        'id': str(user.id),
        'email': user.email,
        'display_name': user.display_name,
        'roles': sorted(user.role_names),
        'status': user.status,
        'created_at': user.created_at.isoformat(),
    }


def _serialize_audit_log(entry: AuditLog) -> dict:
    return {
        'id': str(entry.id),
        'user_id': str(entry.user_id) if entry.user_id else None,
        'event_type': entry.event_type,
        'resource_id': str(entry.resource_id) if entry.resource_id else None,
        'outcome': entry.outcome,
        'ip_address': entry.ip_address,
        'user_agent': entry.user_agent,
        'timestamp': entry.timestamp.isoformat(),
    }


def _parse_positive_int(raw, default: int, maximum: int | None = None) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    if value < 1:
        return default
    return min(value, maximum) if maximum is not None else value


def _parse_date_param(raw):
    if not raw:
        return None
    try:
        return datetime.strptime(raw, '%Y-%m-%d')
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# FR-11: List all users (allowlisted fields only)
# ---------------------------------------------------------------------------

@admin_bp.get('/users')
@require_auth
@require_role('ADMIN')
def list_users():
    users = User.query.order_by(User.created_at.desc()).all()
    return jsonify([_serialize_user(u) for u in users]), 200


# ---------------------------------------------------------------------------
# FR-11: Suspend / reinstate a user
# ---------------------------------------------------------------------------

@admin_bp.patch('/users/<user_id>/status')
@require_auth
@require_role('ADMIN')
def update_user_status(user_id):
    admin = g.current_user
    ip, ua = client_ip(), user_agent()

    try:
        target_uuid = uuid.UUID(user_id)
    except ValueError:
        return jsonify({'error': 'user not found'}), 404

    if target_uuid == admin.id:
        return jsonify({'error': 'Cannot modify your own account'}), 403

    data = request.get_json(silent=True) or {}
    status = data.get('status')
    if status not in _VALID_STATUSES:
        return jsonify({'error': 'status must be one of ACTIVE, SUSPENDED'}), 400

    target = User.query.filter_by(id=target_uuid).first()
    if target is None:
        return jsonify({'error': 'user not found'}), 404

    target.status = status
    db.session.commit()

    log_event('ADMIN_ACTION', 'SUCCESS', ip, user_id=admin.id, resource_id=target.id, user_agent=ua)

    return jsonify(_serialize_user(target)), 200


# ---------------------------------------------------------------------------
# FR-11: Delete a user (cascade removes dependent records)
# ---------------------------------------------------------------------------

@admin_bp.delete('/users/<user_id>')
@require_auth
@require_role('ADMIN')
def delete_user(user_id):
    admin = g.current_user
    ip, ua = client_ip(), user_agent()

    try:
        target_uuid = uuid.UUID(user_id)
    except ValueError:
        return jsonify({'error': 'user not found'}), 404

    if target_uuid == admin.id:
        return jsonify({'error': 'Cannot delete your own account'}), 403

    target = User.query.filter_by(id=target_uuid).first()
    if target is None:
        return jsonify({'error': 'user not found'}), 404

    # Audit log written before deletion so resource_id survives.
    log_event('ADMIN_ACTION', 'SUCCESS', ip, user_id=admin.id, resource_id=target.id, user_agent=ua)

    db.session.delete(target)
    db.session.commit()

    return '', 204


# ---------------------------------------------------------------------------
# FR-11: Set a user's roles (a user may hold several)
# ---------------------------------------------------------------------------

@admin_bp.patch('/users/<user_id>/roles')
@require_auth
@require_role('ADMIN')
def update_user_roles(user_id):
    admin = g.current_user
    ip, ua = client_ip(), user_agent()

    try:
        target_uuid = uuid.UUID(user_id)
    except ValueError:
        return jsonify({'error': 'user not found'}), 404

    if target_uuid == admin.id:
        return jsonify({'error': 'Cannot modify your own account'}), 403

    data = request.get_json(silent=True) or {}
    role_names = data.get('roles')
    if not isinstance(role_names, list) or not role_names:
        return jsonify({'error': 'roles must be a non-empty list'}), 400
    if not all(isinstance(r, str) for r in role_names):
        return jsonify({'error': 'roles must be a list of role names'}), 400

    wanted = set(role_names)
    roles = Role.query.filter(Role.role_name.in_(wanted)).all()
    if len(roles) != len(wanted):
        return jsonify({'error': 'one or more roles are invalid'}), 400

    target = User.query.filter_by(id=target_uuid).first()
    if target is None:
        return jsonify({'error': 'user not found'}), 404

    target.roles = roles
    db.session.commit()

    log_event('ADMIN_ACTION', 'SUCCESS', ip, user_id=admin.id, resource_id=target.id, user_agent=ua)

    return jsonify(_serialize_user(target)), 200


# ---------------------------------------------------------------------------
# SR-16: Paginated, filterable audit log — read-only, no sensitive fields
# ---------------------------------------------------------------------------

@admin_bp.get('/audit-logs')
@require_auth
@require_role('ADMIN')
def list_audit_logs():
    page = _parse_positive_int(request.args.get('page'), default=1)
    page_size = _parse_positive_int(
        request.args.get('page_size'), default=_DEFAULT_PAGE_SIZE, maximum=_MAX_PAGE_SIZE,
    )

    query = AuditLog.query

    event_type = request.args.get('event_type')
    if event_type:
        query = query.filter(AuditLog.event_type == event_type)

    raw_user_id = request.args.get('user_id')
    if raw_user_id:
        try:
            query = query.filter(AuditLog.user_id == uuid.UUID(raw_user_id))
        except ValueError:
            pass  # malformed filter — ignored, not a fatal error

    outcome = request.args.get('outcome')
    if outcome in _VALID_OUTCOMES:
        query = query.filter(AuditLog.outcome == outcome)

    from_date = _parse_date_param(request.args.get('from_date'))
    if from_date:
        query = query.filter(AuditLog.timestamp >= from_date)

    to_date = _parse_date_param(request.args.get('to_date'))
    if to_date:
        query = query.filter(AuditLog.timestamp < to_date + timedelta(days=1))

    total = query.count()
    entries = (
        query.order_by(AuditLog.timestamp.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return jsonify({
        'items': [_serialize_audit_log(e) for e in entries],
        'page': page,
        'page_size': page_size,
        'total': total,
    }), 200
