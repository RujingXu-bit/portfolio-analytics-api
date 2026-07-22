import csv
from collections.abc import Mapping, Sequence
from io import StringIO
from typing import Any

from pydantic import ValidationError

from portfolio_analytics_api.api.schemas import TransactionInput
from portfolio_analytics_api.application import (
    NewTransaction,
    TransactionImportCandidate,
    TransactionImportFormatError,
    TransactionImportIssue,
)

MAX_CSV_BYTES = 1_000_000
MAX_CSV_ROWS = 500
_REQUIRED_HEADERS = {"external_id", "transaction_type", "occurred_at"}
_OPTIONAL_HEADERS = {"symbol", "quantity", "unit_price", "cash_amount", "fees"}
_ALLOWED_HEADERS = _REQUIRED_HEADERS | _OPTIONAL_HEADERS


def parse_transaction_csv(csv_data: bytes) -> tuple[TransactionImportCandidate, ...]:
    if len(csv_data) > MAX_CSV_BYTES:
        raise TransactionImportFormatError(
            f"CSV document exceeds the {MAX_CSV_BYTES}-byte limit"
        )
    try:
        text = csv_data.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise TransactionImportFormatError("CSV document must be UTF-8") from error
    if "\x00" in text:
        raise TransactionImportFormatError("CSV document contains a null byte")

    reader = csv.DictReader(StringIO(text, newline=""), strict=True)
    headers = _validate_headers(reader.fieldnames)
    reader.fieldnames = headers
    candidates: list[TransactionImportCandidate] = []
    try:
        for raw_row in reader:
            if _is_blank_row(raw_row):
                continue
            if len(candidates) >= MAX_CSV_ROWS:
                raise TransactionImportFormatError(
                    f"CSV document exceeds the {MAX_CSV_ROWS}-row limit"
                )
            candidates.append(_parse_row(reader.line_num, raw_row))
    except csv.Error as error:
        raise TransactionImportFormatError("CSV document is malformed") from error

    if not candidates:
        raise TransactionImportFormatError("CSV document has no transaction rows")
    return tuple(candidates)


def _validate_headers(fieldnames: Sequence[str] | None) -> list[str]:
    if not fieldnames:
        raise TransactionImportFormatError("CSV header row is missing")
    headers = [header.strip() for header in fieldnames]
    if any(not header for header in headers):
        raise TransactionImportFormatError("CSV header contains a blank column")
    if len(headers) != len(set(headers)):
        raise TransactionImportFormatError("CSV header contains duplicate columns")
    missing = sorted(_REQUIRED_HEADERS - set(headers))
    if missing:
        raise TransactionImportFormatError(
            f"CSV header is missing required columns: {', '.join(missing)}"
        )
    unexpected = sorted(set(headers) - _ALLOWED_HEADERS)
    if unexpected:
        raise TransactionImportFormatError(
            f"CSV header contains unsupported columns: {', '.join(unexpected)}"
        )
    return headers


def _is_blank_row(row: dict[str | None, str | list[str] | None]) -> bool:
    return all(
        value is None
        or (isinstance(value, str) and not value.strip())
        or (isinstance(value, list) and not any(item.strip() for item in value))
        for value in row.values()
    )


def _parse_row(
    row_number: int,
    raw_row: dict[str | None, str | list[str] | None],
) -> TransactionImportCandidate:
    external_id = _string_value(raw_row.get("external_id"))
    if None in raw_row:
        return TransactionImportCandidate(
            row_number=row_number,
            external_id=external_id or None,
            new_transaction=None,
            issues=(
                TransactionImportIssue(
                    code="extra_columns",
                    message="row contains more values than the header",
                ),
            ),
        )

    payload: dict[str, Any] = {}
    for field in _ALLOWED_HEADERS:
        if field not in raw_row:
            continue
        value = _string_value(raw_row[field])
        if field == "fees" and not value:
            continue
        payload[field] = value if value else None

    try:
        transaction = TransactionInput.model_validate(payload)
    except ValidationError as error:
        issues = tuple(_validation_issue(item) for item in error.errors())
        return TransactionImportCandidate(
            row_number=row_number,
            external_id=external_id or None,
            new_transaction=None,
            issues=issues,
        )

    return TransactionImportCandidate(
        row_number=row_number,
        external_id=transaction.external_id,
        new_transaction=NewTransaction(
            external_id=transaction.external_id,
            transaction_type=transaction.transaction_type,
            occurred_at=transaction.occurred_at,
            symbol=transaction.symbol,
            quantity=transaction.quantity,
            unit_price=transaction.unit_price,
            cash_amount=transaction.cash_amount,
            fees=transaction.fees,
        ),
    )


def _string_value(value: str | list[str] | None) -> str:
    return value.strip() if isinstance(value, str) else ""


def _validation_issue(error: Mapping[str, Any]) -> TransactionImportIssue:
    location = error.get("loc")
    field = str(location[-1]) if isinstance(location, tuple) and location else None
    return TransactionImportIssue(
        code="invalid_field" if field is not None else "invalid_row",
        field=field,
        message=str(error.get("msg", "row validation failed")),
    )
