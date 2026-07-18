from __future__ import annotations

import csv
import io
import uuid
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation

from flask import Blueprint, g, jsonify, request
from sqlalchemy import or_

from app.extensions import db
from app.middleware.auth import require_auth, require_role
from app.models import Category, Transaction
from app.services.audit import log_event
from app.utils.request_meta import client_ip, user_agent

transactions_bp = Blueprint('transactions', __name__, url_prefix='/api/transactions')

# FR-06: GET /api/transactions, POST /api/transactions
# FR-06: PATCH /api/transactions/:id, DELETE /api/transactions/:id
# FR-08: GET /api/dashboard  -> app/routes/dashboard.py
# FR-13: GET /api/transactions/export

# transaction_date may not be dated further ahead than this many days.
_MAX_FUTURE_DAYS = 1

# Fields a client is allowed to change via PATCH.
_EDITABLE_FIELDS = {'transaction_date', 'amount', 'category_id', 'merchant_name', 'description'}


def _parse_date_param(name: str):
    raw = request.args.get(name)
    if not raw:
        return None
    try:
        return datetime.strptime(raw, '%Y-%m-%d').date()
    except ValueError:
        return None


def _serialize(t: Transaction) -> dict:
    return {
        'id': str(t.id),
        'transaction_date': t.transaction_date.isoformat(),
        'amount': str(t.amount),
        'type': t.category.type,
        'category': t.category.name,
        'category_id': str(t.category_id),
        'merchant_name': t.merchant_name,
        'description': t.description,
    }


def _csv_safe(value: str) -> str:
    """Neutralise CSV/formula injection: a leading =,+,-,@,tab,CR makes spreadsheet
    apps evaluate the cell as a formula. Prefix such cells with a single quote."""
    if value and value[0] in ('=', '+', '-', '@', '\t', '\r'):
        return "'" + value
    return value


# ---------------------------------------------------------------------------
# Field validators — shared by create and update. Each returns (ok, value_or_error).
# ---------------------------------------------------------------------------

def _validate_tx_date(raw):
    if not isinstance(raw, str):
        return False, 'transaction_date must be YYYY-MM-DD'
    try:
        tx_date = datetime.strptime(raw, '%Y-%m-%d').date()
    except ValueError:
        return False, 'transaction_date must be YYYY-MM-DD'
    if tx_date > (datetime.utcnow().date() + timedelta(days=_MAX_FUTURE_DAYS)):
        return False, 'transaction_date is too far in the future'
    return True, tx_date


def _validate_amount(raw):
    if isinstance(raw, float):
        # Reject float — precision loss. Client must send amount as a string.
        return False, 'amount must be sent as a string, not a number'
    if not isinstance(raw, (str, int)):
        return False, 'amount must be a string or integer'
    try:
        amount = Decimal(str(raw))
    except (InvalidOperation, ValueError):
        return False, 'amount must be a valid decimal'
    if not amount.is_finite() or amount <= 0:
        return False, 'amount must be a positive decimal'
    if amount.as_tuple().exponent < -2:
        return False, 'amount may have at most 2 decimal places'
    if amount >= Decimal('10000000000'):  # Numeric(12, 2) -> max 10 integer digits
        return False, 'amount is too large'
    return True, amount


def _resolve_category(raw, user):
    """Return (True, Category) for a global or user-owned category, else (False, error)."""
    if not isinstance(raw, str):
        return False, 'category_id must be a valid UUID'
    try:
        category_uuid = uuid.UUID(raw)
    except ValueError:
        return False, 'category_id must be a valid UUID'

    category = Category.query.filter(
        Category.id == category_uuid,
        or_(Category.user_id.is_(None), Category.user_id == user.id),
    ).first()
    if category is None:
        return False, 'category not found'
    return True, category


# ---------------------------------------------------------------------------
# FR-06: List own transactions (object-level scoped to current user)
# ---------------------------------------------------------------------------

@transactions_bp.get('')
@require_auth
@require_role('INDIVIDUAL')
def list_transactions():
    query = (
        Transaction.query
        .filter_by(user_id=g.current_user.id)
    )

    date_from = _parse_date_param('from')
    date_to = _parse_date_param('to')
    if date_from:
        query = query.filter(Transaction.transaction_date >= date_from)
    if date_to:
        query = query.filter(Transaction.transaction_date <= date_to)

    transactions = (
        query.join(Category, Transaction.category_id == Category.id)
        .order_by(Transaction.transaction_date.desc(), Transaction.created_at.desc())
        .all()
    )

    return jsonify([_serialize(t) for t in transactions]), 200


# ---------------------------------------------------------------------------
# FR-13: Export own transactions as CSV (object-level scoped to current user)
# ---------------------------------------------------------------------------

@transactions_bp.get('/export')
@require_auth
@require_role('INDIVIDUAL')
def export_transactions():
    user = g.current_user
    ip = client_ip()
    ua = user_agent()

    rows = (
        Transaction.query
        .filter_by(user_id=user.id)
        .join(Category, Transaction.category_id == Category.id)
        .order_by(Transaction.transaction_date.desc(), Transaction.created_at.desc())
        .all()
    )

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(['date', 'amount', 'category', 'merchant', 'description'])
    for t in rows:
        writer.writerow([
            t.transaction_date.isoformat(),
            str(t.amount),
            _csv_safe(t.category.name),
            _csv_safe(t.merchant_name or ''),
            _csv_safe(t.description or ''),
        ])

    log_event(
        'TRANSACTION_EXPORTED', 'SUCCESS', ip,
        user_id=user.id, user_agent=ua,
    )

    return buf.getvalue(), 200, {
        'Content-Type': 'text/csv; charset=utf-8',
        'Content-Disposition': 'attachment; filename="transactions.csv"',
    }


# ---------------------------------------------------------------------------
# FR-06: Create a transaction (manual entry)
# ---------------------------------------------------------------------------

@transactions_bp.post('')
@require_auth
@require_role('INDIVIDUAL')
def create_transaction():
    user = g.current_user
    ip = client_ip()
    ua = user_agent()

    data = request.get_json(silent=True) or {}

    ok, val = _validate_tx_date(data.get('transaction_date'))
    if not ok:
        return jsonify({'error': val}), 400
    tx_date = val

    ok, val = _validate_amount(data.get('amount'))
    if not ok:
        return jsonify({'error': val}), 400
    amount = val

    ok, val = _resolve_category(data.get('category_id'), user)
    if not ok:
        return jsonify({'error': val}), 404 if val == 'category not found' else 400
    category = val

    # --- optional string fields -------------------------------------------
    merchant_name = data.get('merchant_name')
    if merchant_name is not None:
        if not isinstance(merchant_name, str):
            return jsonify({'error': 'merchant_name must be a string'}), 400
        merchant_name = merchant_name.strip()[:255] or None

    description = data.get('description')
    if description is not None:
        if not isinstance(description, str):
            return jsonify({'error': 'description must be a string'}), 400
        description = description.strip() or None

    transaction = Transaction(
        user_id=user.id,
        category_id=category.id,
        transaction_date=tx_date,
        amount=amount,
        merchant_name=merchant_name,
        description=description,
    )
    db.session.add(transaction)
    db.session.commit()

    log_event(
        'TRANSACTION_CREATED', 'SUCCESS', ip,
        user_id=user.id, resource_id=transaction.id, user_agent=ua,
    )

    return jsonify(_serialize(transaction)), 201


# ---------------------------------------------------------------------------
# FR-06: Update a transaction (partial, object-level scoped to current user)
# ---------------------------------------------------------------------------

@transactions_bp.patch('/<transaction_id>')
@require_auth
@require_role('INDIVIDUAL')
def update_transaction(transaction_id):
    user = g.current_user
    ip = client_ip()
    ua = user_agent()

    # Object-level check: id AND user_id. Unknown/foreign id -> 404 (never reveals existence).
    try:
        tx_uuid = uuid.UUID(transaction_id)
    except ValueError:
        return jsonify({'error': 'transaction not found'}), 404

    transaction = Transaction.query.filter_by(id=tx_uuid, user_id=user.id).first()
    if transaction is None:
        return jsonify({'error': 'transaction not found'}), 404

    data = request.get_json(silent=True) or {}
    if not (_EDITABLE_FIELDS & data.keys()):
        return jsonify({'error': 'no editable fields provided'}), 400

    if 'transaction_date' in data:
        ok, val = _validate_tx_date(data.get('transaction_date'))
        if not ok:
            return jsonify({'error': val}), 400
        transaction.transaction_date = val

    if 'amount' in data:
        ok, val = _validate_amount(data.get('amount'))
        if not ok:
            return jsonify({'error': val}), 400
        transaction.amount = val

    if 'category_id' in data:
        ok, val = _resolve_category(data.get('category_id'), user)
        if not ok:
            return jsonify({'error': val}), 404 if val == 'category not found' else 400
        transaction.category_id = val.id

    if 'merchant_name' in data:
        raw = data.get('merchant_name')
        if raw is None:
            transaction.merchant_name = None
        elif not isinstance(raw, str):
            return jsonify({'error': 'merchant_name must be a string'}), 400
        else:
            transaction.merchant_name = raw.strip()[:255] or None

    if 'description' in data:
        raw = data.get('description')
        if raw is None:
            transaction.description = None
        elif not isinstance(raw, str):
            return jsonify({'error': 'description must be a string'}), 400
        else:
            transaction.description = raw.strip() or None

    db.session.commit()

    log_event(
        'TRANSACTION_UPDATED', 'SUCCESS', ip,
        user_id=user.id, resource_id=transaction.id, user_agent=ua,
    )

    return jsonify(_serialize(transaction)), 200


# ---------------------------------------------------------------------------
# FR-06: Delete ALL of the current user's transactions (bulk clear)
# ---------------------------------------------------------------------------

@transactions_bp.delete('')
@require_auth
@require_role('INDIVIDUAL')
def delete_all_transactions():
    user = g.current_user
    ip = client_ip()
    ua = user_agent()

    # Object-level: scoped to this user only. Bulk DELETE returns the row count.
    deleted = (
        Transaction.query
        .filter_by(user_id=user.id)
        .delete(synchronize_session=False)
    )

    log_event(
        'TRANSACTIONS_CLEARED', 'SUCCESS', ip,
        user_id=user.id, user_agent=ua,
    )
    db.session.commit()

    return jsonify({'deleted_count': deleted}), 200


# ---------------------------------------------------------------------------
# FR-06: Delete a transaction (object-level scoped to current user)
# ---------------------------------------------------------------------------

@transactions_bp.delete('/<transaction_id>')
@require_auth
@require_role('INDIVIDUAL')
def delete_transaction(transaction_id):
    user = g.current_user
    ip = client_ip()
    ua = user_agent()

    try:
        tx_uuid = uuid.UUID(transaction_id)
    except ValueError:
        return jsonify({'error': 'transaction not found'}), 404

    transaction = Transaction.query.filter_by(id=tx_uuid, user_id=user.id).first()
    if transaction is None:
        return jsonify({'error': 'transaction not found'}), 404

    # Audit log written before deletion so resource_id survives.
    log_event(
        'TRANSACTION_DELETED', 'SUCCESS', ip,
        user_id=user.id, resource_id=transaction.id, user_agent=ua,
    )

    db.session.delete(transaction)
    db.session.commit()

    return '', 204
