# CSV Transaction Import

E2.2 adds a preview-first import for an owned Portfolio. The API accepts the CSV
document directly as a UTF-8 `text/csv` request body; it does not accept a file
path, multipart form, spreadsheet formulas, or broker credentials.

Use the checked-in [example CSV](examples/transactions.csv) as a template.

## Columns

The header order is flexible. Unknown or duplicate headers are rejected. These
columns are required in the header and on every transaction row:

- `external_id`: non-blank, at most 100 characters, and stable within the
  Portfolio;
- `transaction_type`: `BUY`, `SELL`, `DEPOSIT`, or `WITHDRAWAL`;
- `occurred_at`: an ISO 8601 datetime with an explicit timezone.

The optional headers are `symbol`, `quantity`, `unit_price`, `cash_amount`, and
`fees`. BUY/SELL rows require symbol, quantity, and unit price and must leave
cash amount blank. DEPOSIT/WITHDRAWAL rows require cash amount and must leave
symbol, quantity, and unit price blank. Blank fees mean zero.

All quantities, money, and fees enter the existing Pydantic and Decimal
boundaries. Quantity supports up to 12 decimal places; price, cash, and fees
support up to 8. The importer never converts financial input through binary
floating point.

## Preview

Preview is write-free:

```bash
curl -X POST \
  http://127.0.0.1:8000/portfolios/<portfolio-id>/transactions/import/preview \
  -H 'Authorization: Bearer <token>' \
  -H 'Content-Type: text/csv' \
  --data-binary @docs/examples/transactions.csv
```

Each non-blank data row retains its reported CSV row number and receives one
status:

- `ready`: valid and would create a transaction;
- `replay`: the same normalized payload already uses this `external_id`;
- `invalid`: field, idempotency, or ledger validation failed.

Every invalid row has structured `errors` containing a stable code, optional
field, and safe message. Preview checks ownership before parsing and simulates
rows from top to bottom against the existing ledger; one invalid row does not
prevent later rows from being evaluated. It is not a reservation, so a write
between preview and commit can change the final status.

## Commit and retry

After reviewing the response, submit the same bytes:

```bash
curl -X POST \
  http://127.0.0.1:8000/portfolios/<portfolio-id>/transactions/import \
  -H 'Authorization: Bearer <token>' \
  -H 'Content-Type: text/csv' \
  --data-binary @docs/examples/transactions.csv
```

Rows are processed top to bottom through the existing `TransactionService`.
Each valid row keeps the normal owner check, Portfolio row lock, Decimal
normalization, domain validation, position replay, database uniqueness, and
commit boundary. The response uses `created`, `replayed`, or `failed` per row;
expected row failures do not roll back successful rows.

Reposting identical CSV bytes is safe because `external_id` is required and
the single-transaction idempotency comparison remains authoritative. A reused
ID with different normalized data fails that row with `idempotency_conflict`.
The importer does not invent IDs because two economically identical broker rows
cannot be safely distinguished without a source-provided reference.

## Limits and file errors

- maximum request size: 1,000,000 bytes;
- maximum non-blank data rows: 500;
- UTF-8 with an optional BOM;
- RFC-style CSV quoting with strict malformed-quote rejection.

Missing/duplicate/unknown headers, invalid UTF-8, null bytes, malformed quoting,
an empty document, and document-level limits return HTTP 422 with
`csv_import_invalid`. Row errors stay inside a successful preview/commit report
so partial outcomes remain explicit. Request bodies and CSV values are excluded
from structured application logs.
