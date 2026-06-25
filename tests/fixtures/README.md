# Mock fixtures

Synthetic, **non-personal** sample files used by the test suites. Safe to commit —
no real account numbers, balances, or transactions. Real statements live in
`data/` (git-ignored) and never belong here.

Each transaction CSV exercises a different code path in
[`services/csv_parser.py`](../../services/csv_parser.py):

| File | Format it exercises |
|---|---|
| `citi-checking.csv` | separate Debit/Credit columns, `MM-DD-YYYY` dates, trailing comma |
| `citi-doublecash.csv` | single signed `Amount` column (purchases negative) |
| `amex.csv` | single `Amount` with charges **positive** → needs `flip_amount_signs` |
| `capitalone.csv` | unsigned `Transaction Amount` + `Transaction Type` (Credit/Debit) |
| `unmatched.csv` | descriptions no seed rule matches → land in `/transactions/review` |
| `schwab-positions.csv` | Schwab "Positions" holdings export ([`holdings_parser.py`](../../services/holdings_parser.py)) |

The accounts these map to (by `institution`) are created by
[`scripts/seed_test_db.py`](../../scripts/seed_test_db.py).
