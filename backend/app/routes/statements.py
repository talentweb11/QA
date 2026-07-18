from __future__ import annotations

import csv
import io
import os
import uuid
from pathlib import Path
from uuid import uuid4

import magic
from flask import Blueprint, current_app, g, jsonify, request
from sqlalchemy import or_

from app import limiter
from app.extensions import db
from app.middleware.auth import require_auth, require_role
from app.models import BankStatement, Category, Transaction
from app.services.audit import log_event
from app.services.statement_parser import ParseError, parse_csv, parse_pdf
from app.services.storage import StorageError, fetch_statement, upload_statement
from app.utils.encryption import hash_file_sha256
from app.utils.request_meta import client_ip, user_agent

statements_bp = Blueprint('statements', __name__, url_prefix='/api/statements')

# FR-07: POST /api/statements/upload
# FR-07: GET  /api/statements


def _uploaded_file_size_bytes(uploaded_file) -> int:
    stream = uploaded_file.stream
    current_position = stream.tell()
    stream.seek(0, io.SEEK_END)
    size = stream.tell()
    stream.seek(current_position)
    return size


def _uploaded_file_mime_type(uploaded_file) -> str | None:
    stream = uploaded_file.stream
    current_position = stream.tell()
    stream.seek(0)
    sample = stream.read(8192)
    stream.seek(current_position)
    mime_type = magic.from_buffer(sample, mime=True)

    if mime_type == 'application/pdf' or sample.startswith(b'%PDF-'):
        return 'application/pdf'

    if mime_type in {'text/csv', 'text/plain'}:
        try:
            sample_text = sample.decode('utf-8-sig')
        except UnicodeDecodeError:
            return None

        try:
            dialect = csv.Sniffer().sniff(sample_text, delimiters=',;\t|')
            rows = list(csv.reader(io.StringIO(sample_text), dialect))
        except csv.Error:
            return None

        if rows and any(len(row) > 1 for row in rows):
            return 'text/csv'

        return None

    if b'\x00' in sample:
        return None

    return None


def _server_generated_filename(original_filename: str) -> str:
    return f'{uuid4()}{Path(original_filename).suffix}'


def _uploaded_file_bytes(uploaded_file) -> bytes:
    stream = uploaded_file.stream
    current_position = stream.tell()
    stream.seek(0)
    file_bytes = stream.read()
    stream.seek(current_position)
    return file_bytes



def _other_categories() -> tuple[Category | None, Category | None]:
    """Resolve the two global fallback categories used for imported transactions."""
    expense = Category.query.filter_by(user_id=None, name='Other Expense', type='EXPENSE').first()
    income = Category.query.filter_by(user_id=None, name='Other Income', type='INCOME').first()
    return expense, income


def _category_lookup(user_id) -> dict:
    """Case-insensitive name -> Category map of everything this user can use:
    global categories (user_id NULL) plus their own custom ones."""
    categories = (
        Category.query
        .filter(or_(Category.user_id.is_(None), Category.user_id == user_id))
        .all()
    )
    return {c.name.strip().lower(): c for c in categories}


def _unknown_categories(rows: list[dict], lookup: dict) -> list[dict]:
    """Distinct file category names not present in `lookup`, each with a suggested
    type derived from the majority amount sign of that name's rows."""
    seen: dict[str, dict] = {}
    for r in rows:
        name = r.get('category_name')
        if not name:
            continue
        key = name.strip().lower()
        if key in lookup:
            continue
        entry = seen.setdefault(key, {'name': name.strip(), 'expense': 0, 'income': 0})
        if r['is_expense']:
            entry['expense'] += 1
        else:
            entry['income'] += 1
    return [
        {'name': e['name'], 'suggested_type': 'EXPENSE' if e['expense'] >= e['income'] else 'INCOME'}
        for e in seen.values()
    ]


def _resolve_row_category(r: dict, lookup: dict, cat_expense: Category, cat_income: Category):
    """Map a parsed row to a Category. A named category resolves via `lookup`
    (None if it still does not exist); a blank category falls back to Other."""
    name = r.get('category_name')
    if name:
        return lookup.get(name.strip().lower())
    return cat_expense if r['is_expense'] else cat_income


# ---------------------------------------------------------------------------
# FR-07: Upload + parse + import a bank statement
# ---------------------------------------------------------------------------

@statements_bp.post('/upload')
@require_auth
@require_role('INDIVIDUAL')
@limiter.limit('20 per hour', key_func=lambda: str(g.current_user.id))
def upload():
    ip, ua = client_ip(), user_agent()
    user = g.current_user

    file = request.files.get('file')
    if file is None or not file.filename:
        return jsonify({'error': 'No file provided'}), 400

    original_name = file.filename
    ext = os.path.splitext(original_name)[1].lower().lstrip('.')

    # 1. Size check — baseline byte count (MAX_CONTENT_LENGTH also rejects at the WSGI layer).
    max_upload_size_bytes = current_app.config['MAX_UPLOAD_SIZE_MB'] * 1024 * 1024
    if _uploaded_file_size_bytes(file) > max_upload_size_bytes:
        log_event('STATEMENT_UPLOADED', 'FAILURE', ip, user_id=user.id, user_agent=ua)
        return jsonify({'error': 'File too large'}), 413

    # 2. Type check — CSV only. Extension AND magic-byte MIME must both be CSV.
    mime_type = _uploaded_file_mime_type(file)
    if ext != 'csv' or mime_type != 'text/csv':
        log_event('STATEMENT_UPLOADED', 'FAILURE', ip, user_id=user.id, user_agent=ua)
        return jsonify({'error': 'Unsupported file type. Only CSV files are accepted.'}), 415

    # 3. Generate random server-generated filename (never trust client filename).
    server_filename = _server_generated_filename(original_name)
    content_type = 'text/csv'

    # 4. Read and store the raw file in the private Supabase bucket.
    file_bytes = _uploaded_file_bytes(file)
    if not file_bytes:
        return jsonify({'error': 'Empty file'}), 400

    object_path = f'{user.id}/{server_filename}'
    try:
        storage_path = upload_statement(object_path, file_bytes, content_type)
    except StorageError:
        current_app.logger.exception('statement storage upload failed')
        log_event('STATEMENT_UPLOADED', 'FAILURE', ip, user_id=user.id, user_agent=ua)
        return jsonify({'error': 'Failed to store file'}), 502

    # 5. Compute integrity hash.
    file_hash = hash_file_sha256(file_bytes)

    # 6. Parse transactions from file.
    rows: list[dict] = []
    skipped = 0
    parse_ok = True
    try:
        rows, skipped = parse_csv(file_bytes)
    except ParseError:
        parse_ok = False
    if not rows:
        parse_ok = False

    def _new_statement(status: str) -> BankStatement:
        stmt = BankStatement(
            user_id=user.id,
            file_name=original_name[:255],
            storage_path=storage_path,
            file_hash=file_hash,
            status=status,
            # account_number_encrypted left null — TODO: extract account number then encrypt_field
        )
        db.session.add(stmt)
        return stmt

    # 6a. Nothing parsed — record a FAILED statement, import nothing.
    if not parse_ok:
        statement = _new_statement('FAILED')
        db.session.commit()
        log_event('STATEMENT_UPLOADED', 'FAILURE', ip, user_id=user.id, resource_id=statement.id, user_agent=ua)
        return jsonify({
            'statement_id': str(statement.id),
            'status': 'FAILED',
            'imported_count': 0,
            'skipped_count': skipped,
        }), 201

    # 6b. Any file category we don't recognise yet -> hold (PENDING) for the user
    #     to create it, then confirm via POST /<id>/import. No transactions inserted.
    lookup = _category_lookup(user.id)
    unknown = _unknown_categories(rows, lookup)
    if unknown:
        statement = _new_statement('PENDING')
        db.session.commit()
        log_event('STATEMENT_UPLOADED', 'SUCCESS', ip, user_id=user.id, resource_id=statement.id, user_agent=ua)
        return jsonify({
            'statement_id': str(statement.id),
            'status': 'NEEDS_CATEGORIES',
            'unknown_categories': unknown,
            'total_rows': len(rows),
            'skipped_count': skipped,
        }), 201

    # 6c. All categories known — import immediately.
    cat_expense, cat_income = _other_categories()
    if not cat_expense or not cat_income:
        current_app.logger.error('Global "Other" categories missing from categories table')
        log_event('STATEMENT_UPLOADED', 'FAILURE', ip, user_id=user.id, user_agent=ua)
        return jsonify({'error': 'Server configuration error'}), 500

    statement = _new_statement('PROCESSED')
    db.session.flush()  # assign statement.id before linking transactions

    imported = 0
    for r in rows:
        category = _resolve_row_category(r, lookup, cat_expense, cat_income)
        db.session.add(Transaction(
            user_id=user.id,
            statement_id=statement.id,
            category_id=category.id,
            transaction_date=r['transaction_date'],
            amount=r['amount'],
            merchant_name=r['merchant_name'],
            description=r['description'],
        ))
        imported += 1

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception('failed to import statement transactions')
        log_event('STATEMENT_UPLOADED', 'FAILURE', ip, user_id=user.id, user_agent=ua)
        return jsonify({'error': 'Failed to import transactions'}), 500

    log_event('STATEMENT_UPLOADED', 'SUCCESS', ip, user_id=user.id, resource_id=statement.id, user_agent=ua)

    return jsonify({
        'statement_id': str(statement.id),
        'status': 'PROCESSED',
        'imported_count': imported,
        'skipped_count': skipped,
    }), 201


# ---------------------------------------------------------------------------
# FR-07: List current user's statements
# ---------------------------------------------------------------------------

@statements_bp.get('')
@require_auth
@require_role('INDIVIDUAL')
def list_statements():
    statements = (
        BankStatement.query
        .filter_by(user_id=g.current_user.id)
        .order_by(BankStatement.uploaded_at.desc())
        .all()
    )
    # storage_path and file_hash are deliberately never returned.
    return jsonify([
        {
            'id': str(s.id),
            'file_name': s.file_name,
            'status': s.status,
            'uploaded_at': s.uploaded_at.isoformat(),
        }
        for s in statements
    ]), 200

@statements_bp.get('/<statement_id>')
@require_auth
@require_role('INDIVIDUAL')
def get_statement(statement_id):
  
    ip, ua = client_ip(), user_agent()
    user = g.current_user

    # Fetch statement (verify ownership and get stored hash)
    statement = BankStatement.query.filter_by(
        id=statement_id,
        user_id=user.id
    ).first()

    if not statement:
        return jsonify({'error': 'Statement not found'}), 404

    # Retrieve file from Supabase
    try:
        file_bytes = fetch_statement(statement.storage_path)
    except StorageError:
        current_app.logger.exception('statement retrieval failed')
        log_event('STATEMENT_RETRIEVED', 'FAILURE', ip, user_id=user.id, user_agent=ua)
        return jsonify({'error': 'Failed to retrieve file'}), 502

    # Verify integrity by comparing hashes
    computed_hash = hash_file_sha256(file_bytes)
    if computed_hash != statement.file_hash:
        current_app.logger.error(f'Hash mismatch for statement {statement.id}')
        log_event('STATEMENT_RETRIEVED', 'FAILURE', ip, user_id=user.id, user_agent=ua)
        return jsonify({'error': 'File integrity check failed'}), 409

    log_event('STATEMENT_RETRIEVED', 'SUCCESS', ip, user_id=user.id, resource_id=statement.id, user_agent=ua)

    # Return file with appropriate content type
    content_type = 'text/csv' if statement.file_name.endswith('.csv') else 'application/pdf'
    return file_bytes, 200, {
        'Content-Disposition': f'attachment; filename="{statement.file_name}"',
        'Content-Type': content_type,
    }


# ---------------------------------------------------------------------------
# FR-07: Confirm import of a PENDING statement (after the user created the
# categories its rows referenced). Re-reads the stored file, re-verifies its
# integrity hash, maps every row's category, and inserts the transactions.
# ---------------------------------------------------------------------------

@statements_bp.post('/<statement_id>/import')
@require_auth
@require_role('INDIVIDUAL')
def import_statement(statement_id):
    ip, ua = client_ip(), user_agent()
    user = g.current_user

    # Object-level check: malformed / unknown / foreign id -> 404 (never reveals existence).
    try:
        stmt_uuid = uuid.UUID(statement_id)
    except ValueError:
        return jsonify({'error': 'Statement not found'}), 404

    statement = BankStatement.query.filter_by(id=stmt_uuid, user_id=user.id).first()
    if statement is None:
        return jsonify({'error': 'Statement not found'}), 404

    # Only a held statement may be imported — guards against double import.
    if statement.status != 'PENDING':
        return jsonify({'error': 'Statement has already been processed'}), 409

    # Re-fetch the stored file and re-verify integrity (SR-05).
    try:
        file_bytes = fetch_statement(statement.storage_path)
    except StorageError:
        current_app.logger.exception('statement retrieval failed')
        log_event('STATEMENT_IMPORTED', 'FAILURE', ip, user_id=user.id, resource_id=statement.id, user_agent=ua)
        return jsonify({'error': 'Failed to retrieve file'}), 502

    if hash_file_sha256(file_bytes) != statement.file_hash:
        current_app.logger.error(f'Hash mismatch for statement {statement.id}')
        log_event('STATEMENT_IMPORTED', 'FAILURE', ip, user_id=user.id, resource_id=statement.id, user_agent=ua)
        return jsonify({'error': 'File integrity check failed'}), 409

    ext = os.path.splitext(statement.file_name)[1].lower().lstrip('.')
    try:
        rows, skipped = parse_csv(file_bytes) if ext == 'csv' else parse_pdf(file_bytes)
    except ParseError:
        rows, skipped = [], 0
    if not rows:
        return jsonify({'error': 'No transactions could be read from this statement'}), 422

    # Any named category still missing -> bounce back so the user can create it.
    lookup = _category_lookup(user.id)
    unresolved = [u['name'] for u in _unknown_categories(rows, lookup)]
    if unresolved:
        return jsonify({
            'error': 'Some categories in this statement do not exist yet',
            'unresolved_categories': unresolved,
        }), 400

    cat_expense, cat_income = _other_categories()
    if not cat_expense or not cat_income:
        current_app.logger.error('Global "Other" categories missing from categories table')
        return jsonify({'error': 'Server configuration error'}), 500

    imported = 0
    for r in rows:
        category = _resolve_row_category(r, lookup, cat_expense, cat_income)
        db.session.add(Transaction(
            user_id=user.id,
            statement_id=statement.id,
            category_id=category.id,
            transaction_date=r['transaction_date'],
            amount=r['amount'],
            merchant_name=r['merchant_name'],
            description=r['description'],
        ))
        imported += 1

    statement.status = 'PROCESSED'
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception('failed to import statement transactions')
        log_event('STATEMENT_IMPORTED', 'FAILURE', ip, user_id=user.id, resource_id=statement.id, user_agent=ua)
        return jsonify({'error': 'Failed to import transactions'}), 500

    log_event('STATEMENT_IMPORTED', 'SUCCESS', ip, user_id=user.id, resource_id=statement.id, user_agent=ua)

    return jsonify({
        'statement_id': str(statement.id),
        'status': 'PROCESSED',
        'imported_count': imported,
        'skipped_count': skipped,
    }), 200
