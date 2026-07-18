from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from app.services.statement_parser import ParseError, parse_csv

FIXTURE = Path(__file__).parent / 'fixtures' / 'sample_statement.csv'


def _csv(text: str) -> bytes:
    return text.encode('utf-8')


# ============================================================================
# parse_csv
# ============================================================================

def test_sample_fixture_imports_valid_rows():
    rows, skipped = parse_csv(FIXTURE.read_bytes())
    # 5 valid rows; broken date + zero amount are skipped.
    assert len(rows) == 5
    assert skipped == 2


def test_amount_sign_maps_to_is_expense():
    rows, _ = parse_csv(FIXTURE.read_bytes())
    by_merchant = {r['merchant_name']: r for r in rows}

    assert by_merchant['NTUC FairPrice']['is_expense'] is True
    assert by_merchant['NTUC FairPrice']['amount'] == Decimal('45.20')

    assert by_merchant['ACME Corp']['is_expense'] is False
    assert by_merchant['ACME Corp']['amount'] == Decimal('5000.00')


def test_parenthesised_amount_is_negative_expense():
    rows, _ = parse_csv(FIXTURE.read_bytes())
    coffee = next(r for r in rows if r['merchant_name'] == 'Starbucks')
    assert coffee['is_expense'] is True
    assert coffee['amount'] == Decimal('6.50')


def test_currency_symbol_and_thousands_separator():
    data = _csv('Date,Amount,Description\n2026-02-01,"$1,234.56",Big buy\n')
    rows, skipped = parse_csv(data)
    assert skipped == 0
    assert rows[0]['amount'] == Decimal('1234.56')
    assert rows[0]['is_expense'] is False
    assert rows[0]['transaction_date'] == date(2026, 2, 1)


def test_separate_debit_credit_columns():
    data = _csv(
        'Posting Date,Details,Debit,Credit\n'
        '03/02/2026,Rent,1500.00,\n'
        '04/02/2026,Salary,,3000.00\n'
    )
    rows, skipped = parse_csv(data)
    assert skipped == 0
    debit = next(r for r in rows if r['description'] == 'Rent')
    credit = next(r for r in rows if r['description'] == 'Salary')
    assert debit['is_expense'] is True and debit['amount'] == Decimal('1500.00')
    assert credit['is_expense'] is False and credit['amount'] == Decimal('3000.00')


def test_alternate_date_format():
    data = _csv('Date,Amount\n15/03/2026,-10.00\n')
    rows, _ = parse_csv(data)
    assert rows[0]['transaction_date'] == date(2026, 3, 15)


def test_unrecognizable_headers_raise_parse_error():
    data = _csv('Foo,Bar,Baz\n1,2,3\n')
    with pytest.raises(ParseError):
        parse_csv(data)


def test_all_malformed_rows_returns_empty_not_error():
    data = _csv('Date,Amount\nbad,bad\n,\n')
    rows, skipped = parse_csv(data)
    assert rows == []
    assert skipped == 2
