from __future__ import annotations

import uuid

from flask import Blueprint, g, jsonify, request
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.middleware.auth import require_auth, require_role
from app.models import Category, Transaction
from app.services.audit import log_event
from app.utils.request_meta import client_ip, user_agent

categories_bp = Blueprint('categories', __name__, url_prefix='/api/categories')

# FR-06: GET  /api/categories
# FR-06: POST /api/categories
# FR-06: DELETE /api/categories/:id

_VALID_TYPES = {'INCOME', 'EXPENSE'}


def _serialize(c: Category) -> dict:
    return {
        'id': str(c.id),
        'name': c.name,
        'type': c.type,
        'is_global': c.user_id is None,
    }


# ---------------------------------------------------------------------------
# GET /api/categories — global (user_id NULL) + current user's custom
# ---------------------------------------------------------------------------

@categories_bp.get('')
@require_auth
@require_role('INDIVIDUAL')
def list_categories():
    categories = (
        Category.query
        .filter(or_(Category.user_id.is_(None), Category.user_id == g.current_user.id))
        .order_by(Category.user_id.isnot(None), Category.name)
        .all()
    )
    return jsonify([_serialize(c) for c in categories]), 200


# ---------------------------------------------------------------------------
# POST /api/categories — create a custom category for the current user
# ---------------------------------------------------------------------------

@categories_bp.post('')
@require_auth
@require_role('INDIVIDUAL')
def create_category():
    user = g.current_user
    ip, ua = client_ip(), user_agent()

    data = request.get_json(silent=True) or {}

    raw_name = data.get('name')
    if not isinstance(raw_name, str):
        return jsonify({'error': 'name is required'}), 400
    name = raw_name.strip()
    if not name:
        return jsonify({'error': 'name must be a non-empty string'}), 400
    if len(name) > 100:
        return jsonify({'error': 'name must be 100 characters or fewer'}), 400

    cat_type = data.get('type')
    if cat_type not in _VALID_TYPES:
        return jsonify({'error': 'type must be one of INCOME, EXPENSE'}), 400

    category = Category(user_id=user.id, name=name, type=cat_type)
    db.session.add(category)
    try:
        db.session.commit()
    except IntegrityError:
        # Partial unique index (user_id, name) rejected a duplicate.
        db.session.rollback()
        return jsonify({'error': 'A category with this name already exists'}), 409

    log_event(
        'CATEGORY_CREATED', 'SUCCESS', ip,
        user_id=user.id, resource_id=category.id, user_agent=ua,
    )

    return jsonify(_serialize(category)), 201


# ---------------------------------------------------------------------------
# DELETE /api/categories/<id> — own categories only, not if referenced
# ---------------------------------------------------------------------------

@categories_bp.delete('/<category_id>')
@require_auth
@require_role('INDIVIDUAL')
def delete_category(category_id):
    user = g.current_user
    ip, ua = client_ip(), user_agent()

    # Malformed id -> 404 (never reveals existence).
    try:
        cat_uuid = uuid.UUID(category_id)
    except ValueError:
        return jsonify({'error': 'category not found'}), 404

    # Object-level check: scoping by user_id means a global category (user_id NULL)
    # never matches, so globals cannot be deleted.
    category = Category.query.filter_by(id=cat_uuid, user_id=user.id).first()
    if category is None:
        return jsonify({'error': 'category not found'}), 404

    # Refuse deletion while transactions still reference it (clean 409 message).
    if Transaction.query.filter_by(category_id=cat_uuid).first() is not None:
        return jsonify({'error': 'Category is in use by existing transactions'}), 409

    category_id_str = category.id
    db.session.delete(category)
    try:
        db.session.commit()
    except IntegrityError:
        # Backstop against a race: a transaction referenced it after the check above.
        db.session.rollback()
        return jsonify({'error': 'Category is in use by existing transactions'}), 409

    log_event(
        'CATEGORY_DELETED', 'SUCCESS', ip,
        user_id=user.id, resource_id=category_id_str, user_agent=ua,
    )

    return '', 204
