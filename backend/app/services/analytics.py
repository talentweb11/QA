"""Spending analytics aggregation, parameterised by user_id.

Single source of truth for the aggregated datasets shared by household summary
(FR-15) and advisor analytics (FR-16). All sums run in the database (D-03) —
nothing here decrypts anything, and no raw account numbers are ever read.

NOTE: `routes/dashboard.py` now delegates to `full_analytics()` here (the
coordinated dedup flagged with its owner, Wen Yuan), so the owner dashboard
(FR-08), the household summary (FR-15), and the advisor analytics (FR-16) all
share this single implementation instead of re-forking the aggregation logic.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import func

from app.extensions import db
from app.models import Category, Transaction

TREND_MONTHS = 6


def _month_start(d: date) -> date:
    return d.replace(day=1)


def _add_month(d: date) -> date:
    """First day of the month after `d` (d is expected to be a month start)."""
    if d.month == 12:
        return date(d.year + 1, 1, 1)
    return date(d.year, d.month + 1, 1)


def _shift_months_back(d: date, n: int) -> date:
    year, month = d.year, d.month - n
    while month <= 0:
        month += 12
        year -= 1
    return date(year, month, 1)


def _month_label(d: date) -> str:
    return f'{d.year:04d}-{d.month:02d}'


def spending_by_category(user_id) -> list[dict]:
    """Current-month expense totals grouped by category name, largest first."""
    today = datetime.utcnow().date()
    month_start = _month_start(today)
    next_month_start = _add_month(month_start)

    rows = (
        db.session.query(Category.name, func.sum(Transaction.amount))
        .join(Category, Transaction.category_id == Category.id)
        .filter(
            Transaction.user_id == user_id,
            Category.type == 'EXPENSE',
            Transaction.transaction_date >= month_start,
            Transaction.transaction_date < next_month_start,
        )
        .group_by(Category.name)
        .order_by(func.sum(Transaction.amount).desc())
        .all()
    )
    return [{'category': name, 'total': str(total)} for name, total in rows]


def monthly_trend(user_id, months: int = TREND_MONTHS) -> list[dict]:
    """Spend vs income per month for the last `months` months, zero-filled."""
    today = datetime.utcnow().date()
    month_start = _month_start(today)
    trend_start = _shift_months_back(month_start, months - 1)

    rows = (
        db.session.query(
            func.to_char(Transaction.transaction_date, 'YYYY-MM'),
            Category.type,
            func.sum(Transaction.amount),
        )
        .join(Category, Transaction.category_id == Category.id)
        .filter(
            Transaction.user_id == user_id,
            Transaction.transaction_date >= trend_start,
        )
        .group_by(func.to_char(Transaction.transaction_date, 'YYYY-MM'), Category.type)
        .all()
    )

    buckets: dict[str, dict[str, Decimal]] = {}
    cursor = trend_start
    for _ in range(months):
        buckets[_month_label(cursor)] = {'spend': Decimal('0'), 'income': Decimal('0')}
        cursor = _add_month(cursor)

    for month_key, cat_type, total in rows:
        bucket = buckets.get(month_key)
        if bucket is None:
            continue  # defensive: outside the window
        if cat_type == 'INCOME':
            bucket['income'] += total
        elif cat_type == 'EXPENSE':
            bucket['spend'] += total

    return [
        {'month': label, 'spend': str(b['spend']), 'income': str(b['income'])}
        for label, b in buckets.items()
    ]


def top_merchants(user_id, limit: int = 5) -> list[dict]:
    """Top merchants by current-month expense spend (merchant name required)."""
    today = datetime.utcnow().date()
    month_start = _month_start(today)
    next_month_start = _add_month(month_start)

    rows = (
        db.session.query(Transaction.merchant_name, func.sum(Transaction.amount))
        .join(Category, Transaction.category_id == Category.id)
        .filter(
            Transaction.user_id == user_id,
            Category.type == 'EXPENSE',
            Transaction.merchant_name.isnot(None),
            Transaction.transaction_date >= month_start,
            Transaction.transaction_date < next_month_start,
        )
        .group_by(Transaction.merchant_name)
        .order_by(func.sum(Transaction.amount).desc())
        .limit(limit)
        .all()
    )
    return [{'merchant': name, 'total': str(total)} for name, total in rows]


def household_summary(user_id) -> dict:
    """Aggregated SUMMARY_ONLY view of one user: category spend + monthly trend.

    Deliberately omits merchant-level detail — household members get a summary,
    not a transaction-level view.
    """
    return {
        'spending_by_category': spending_by_category(user_id),
        'monthly_trend': monthly_trend(user_id),
    }


def full_analytics(user_id) -> dict:
    """Full FULL_VIEW analytics for one user — the same three datasets as
    GET /api/dashboard (category spend, monthly trend, top merchants).
    """
    month_start = _month_start(datetime.utcnow().date())
    return {
        'month': _month_label(month_start),
        'spending_by_category': spending_by_category(user_id),
        'monthly_trend': monthly_trend(user_id),
        'top_merchants': top_merchants(user_id),
    }
