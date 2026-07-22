from decimal import Decimal
from pathlib import Path

import pytest

from portfolio_analytics_api.api.csv_import import (
    MAX_CSV_BYTES,
    MAX_CSV_ROWS,
    parse_transaction_csv,
)
from portfolio_analytics_api.application import TransactionImportFormatError
from portfolio_analytics_api.domain import TransactionType


def test_parser_normalizes_valid_utf8_bom_rows() -> None:
    csv_data = (
        "\ufeff external_id , transaction_type , occurred_at , symbol , quantity ,"
        " unit_price , cash_amount , fees\n"
        " deposit-1 , DEPOSIT , 2026-01-01T09:00:00Z ,,,,1000,\n"
        " buy-1 , BUY , 2026-01-02T09:00:00+01:00 , aapl ,2.5,100.25,,0.10\n"
    ).encode()

    rows = parse_transaction_csv(csv_data)

    assert [row.row_number for row in rows] == [2, 3]
    assert all(not row.issues for row in rows)
    assert rows[0].external_id == "deposit-1"
    assert rows[0].new_transaction is not None
    assert rows[0].new_transaction.transaction_type is TransactionType.DEPOSIT
    assert rows[0].new_transaction.cash_amount == Decimal("1000")
    assert rows[0].new_transaction.fees == Decimal("0")
    assert rows[1].new_transaction is not None
    assert rows[1].new_transaction.symbol == "aapl"
    assert rows[1].new_transaction.quantity == Decimal("2.5")


def test_parser_keeps_valid_rows_and_explains_invalid_rows() -> None:
    rows = parse_transaction_csv(
        b"external_id,transaction_type,occurred_at,symbol,quantity,unit_price\n"
        b"ok,BUY,2026-01-02T09:00:00Z,AAPL,2,100\n"
        b"bad,SELL,not-a-date,AAPL,-1,100\n"
        b"too,many,columns,for,this,row,here,extra\n"
    )

    assert rows[0].new_transaction is not None
    assert rows[1].new_transaction is None
    assert {issue.field for issue in rows[1].issues} == {"occurred_at", "quantity"}
    assert all(issue.code == "invalid_field" for issue in rows[1].issues)
    assert rows[2].new_transaction is None
    assert rows[2].issues[0].code == "extra_columns"


@pytest.mark.parametrize(
    ("csv_data", "message"),
    [
        (b"", "header row"),
        (b"external_id,occurred_at\na,2026-01-01T00:00:00Z\n", "required"),
        (
            b"external_id,transaction_type,occurred_at,unknown\n"
            b"a,BUY,2026-01-01T00:00:00Z,x\n",
            "unsupported",
        ),
        (
            b"external_id,external_id,transaction_type,occurred_at\n",
            "duplicate",
        ),
        (b"external_id,transaction_type,occurred_at\n", "no transaction"),
        (b'external_id,transaction_type,occurred_at\n"unterminated', "malformed"),
        (b"external_id,transaction_type,occurred_at\n\x00,BUY,x\n", "null byte"),
        (b"\xff\xfe", "UTF-8"),
    ],
)
def test_parser_rejects_file_level_format_errors(
    csv_data: bytes,
    message: str,
) -> None:
    with pytest.raises(TransactionImportFormatError, match=message):
        parse_transaction_csv(csv_data)


def test_parser_enforces_byte_and_row_limits() -> None:
    with pytest.raises(TransactionImportFormatError, match="byte limit"):
        parse_transaction_csv(b"x" * (MAX_CSV_BYTES + 1))

    header = b"external_id,transaction_type,occurred_at\n"
    row = b"id,DEPOSIT,2026-01-01T00:00:00Z\n"
    with pytest.raises(TransactionImportFormatError, match="row limit"):
        parse_transaction_csv(header + row * (MAX_CSV_ROWS + 1))


def test_checked_in_example_is_a_valid_reusable_template() -> None:
    rows = parse_transaction_csv(Path("docs/examples/transactions.csv").read_bytes())

    assert len(rows) == 2
    assert all(row.new_transaction is not None and not row.issues for row in rows)
