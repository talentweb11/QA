"""Bank statement parsers (CSV + PDF).

Pure parsing logic — no database, no I/O beyond the in-memory file bytes.
Each parser returns ``(rows, skipped)`` where ``rows`` is a list of normalized
dicts and ``skipped`` is the count of malformed rows that were dropped.

Normalized row shape::

    {
        'transaction_date': datetime.date,
        'amount': decimal.Decimal,   # always positive magnitude
        'is_expense': bool,          # True for debits, False for credits
        'merchant_name': str | None,
        'description': str | None,
    }
"""

from __future__ import annotations

import csv
import io
import logging
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

logger = logging.getLogger(__name__)


class ParseError(Exception):
    """Raised when a statement cannot be parsed at all (unrecognizable format)."""


# Header aliases — matched case-insensitively after stripping.
_DATE_KEYS = ('transaction_date', 'date', 'posting date', 'posted date', 'txn date')
_AMOUNT_KEYS = ('amount', 'value', 'transaction amount')
_DEBIT_KEYS = ('debit', 'withdrawal', 'money out', 'paid out')
_CREDIT_KEYS = ('credit', 'deposit', 'money in', 'paid in')
_DESC_KEYS = ('description', 'details', 'narrative', 'memo', 'reference', 'particulars')
_MERCHANT_KEYS = ('merchant', 'merchant_name', 'payee', 'name')
_CATEGORY_KEYS = ('category', 'categories')

_DATE_FORMATS = ('%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y', '%d-%m-%Y', '%Y/%m/%d', '%d %b %Y', '%d %B %Y')


def _pick(headers_lower: dict, keys: tuple) -> str | None:
    """Return the original header name whose lowered form matches one of keys."""
    for key in keys:
        if key in headers_lower:
            return headers_lower[key]
    return None


def _parse_date(raw: str) -> date | None:
    raw = (raw or '').strip()
    if not raw:
        return None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def _parse_amount(raw: str) -> tuple[Decimal, bool] | None:
    """Parse a money string. Returns (magnitude, is_negative) or None if invalid.

    Handles ``$``, thousands separators, and parenthesised negatives ``(12.34)``.
    """
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None

    negative = False
    if text.startswith('(') and text.endswith(')'):
        negative = True
        text = text[1:-1]
    text = text.replace('$', '').replace(',', '').replace(' ', '')
    if text.startswith('-'):
        negative = True
        text = text[1:]
    if text.startswith('+'):
        text = text[1:]
    if not text:
        return None

    try:
        value = Decimal(text)
    except InvalidOperation:
        return None
    return value, negative


def _normalize_row(row: dict, cols: dict) -> dict | None:
    """Turn a raw {header: value} row into a normalized transaction dict.

    ``cols`` maps logical field -> actual header name (or None).
    Returns None for malformed rows (caller counts them as skipped).
    """
    txn_date = _parse_date(row.get(cols['date'], '')) if cols['date'] else None
    if txn_date is None:
        return None

    amount = None
    is_expense = None

    # Preferred: a single signed amount column.
    if cols['amount']:
        parsed = _parse_amount(row.get(cols['amount'], ''))
        if parsed is not None:
            amount, is_expense = parsed[0], parsed[1]

    # Fallback: separate debit / credit columns.
    if amount is None and (cols['debit'] or cols['credit']):
        debit = _parse_amount(row.get(cols['debit'], '')) if cols['debit'] else None
        credit = _parse_amount(row.get(cols['credit'], '')) if cols['credit'] else None
        if debit is not None and debit[0] != 0:
            amount, is_expense = debit[0], True
        elif credit is not None and credit[0] != 0:
            amount, is_expense = credit[0], False

    if amount is None or amount == 0:
        return None

    merchant = (row.get(cols['merchant']) or '').strip() if cols['merchant'] else None
    description = (row.get(cols['description']) or '').strip() if cols['description'] else None
    category = (row.get(cols['category']) or '').strip() if cols['category'] else None

    return {
        'transaction_date': txn_date,
        'amount': abs(amount),
        'is_expense': bool(is_expense),
        'merchant_name': merchant[:255] or None if merchant else None,
        'description': description or None,
        # Category name as written in the file (None when absent). The caller maps
        # it to a Category row; unknown names drive the create-categories flow.
        'category_name': category[:100] or None if category else None,
    }


def _map_columns(headers: list[str]) -> dict:
    headers_lower = {h.strip().lower(): h for h in headers if h}
    cols = {
        'date': _pick(headers_lower, _DATE_KEYS),
        'amount': _pick(headers_lower, _AMOUNT_KEYS),
        'debit': _pick(headers_lower, _DEBIT_KEYS),
        'credit': _pick(headers_lower, _CREDIT_KEYS),
        'description': _pick(headers_lower, _DESC_KEYS),
        'merchant': _pick(headers_lower, _MERCHANT_KEYS),
        'category': _pick(headers_lower, _CATEGORY_KEYS),
    }
    return cols


def _rows_from_records(records: list[dict], headers: list[str]) -> tuple[list[dict], int]:
    cols = _map_columns(headers)
    if not cols['date'] or not (cols['amount'] or cols['debit'] or cols['credit']):
        raise ParseError('Could not find date and amount columns in statement')

    rows: list[dict] = []
    skipped = 0
    for record in records:
        normalized = _normalize_row(record, cols)
        if normalized is None:
            skipped += 1
        else:
            rows.append(normalized)
    return rows, skipped


def parse_csv(file_bytes: bytes) -> tuple[list[dict], int]:
    """Parse a CSV bank statement into normalized transaction rows."""
    try:
        text = file_bytes.decode('utf-8-sig')
    except UnicodeDecodeError:
        text = file_bytes.decode('latin-1', errors='replace')

    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise ParseError('CSV has no header row')

    records = list(reader)
    return _rows_from_records(records, list(reader.fieldnames))


def parse_pdf(file_bytes: bytes) -> tuple[list[dict], int]:
    """Best-effort extraction of transactions from a PDF bank statement.

    Returns ``([], 0)`` rather than raising when no tables/rows are found, so the
    caller can mark the statement FAILED without a 500.
    """
    try:
        import pdfplumber
    except ImportError as exc:  # pragma: no cover - dependency guard
        raise ParseError('PDF parsing is not available (pdfplumber not installed)') from exc

    all_rows: list[dict] = []
    total_skipped = 0
    try:
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            for page in pdf.pages:
                for table in page.extract_tables() or []:
                    if not table or len(table) < 2:
                        continue
                    headers = [(c or '').strip() for c in table[0]]
                    cols = _map_columns(headers)
                    if not cols['date'] or not (cols['amount'] or cols['debit'] or cols['credit']):
                        continue
                    records = [dict(zip(headers, row)) for row in table[1:]]
                    rows, skipped = _rows_from_records(records, headers)
                    all_rows.extend(rows)
                    total_skipped += skipped
    except ParseError:
        raise
    except Exception:
        logger.warning('PDF extraction failed', exc_info=True)
        return [], 0

    return all_rows, total_skipped
