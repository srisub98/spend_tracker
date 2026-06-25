import uuid
import json
import pandas as pd
from services.rules import apply_rules, load_rules

# Column name aliases — maps common bank CSV headers to our standard names
DATE_COLS    = ["date", "trans date", "transaction date", "posted date", "value date", "activity date"]
DESC_COLS    = ["description", "memo", "payee", "narrative", "details", "transaction description", "merchant"]
AMOUNT_COLS  = ["amount", "transaction amount"]
DEBIT_COLS   = ["debit", "withdrawal", "debit amount"]
CREDIT_COLS  = ["credit", "deposit", "credit amount"]
TYPE_COLS    = ["transaction type", "type"]


def _find_col(df_cols, candidates):
    lower = [c.lower().strip() for c in df_cols]
    for candidate in candidates:
        if candidate in lower:
            return df_cols[lower.index(candidate)]
    return None


def read_headers(filepath):
    """Just the CSV header row — for the mapping UI when auto-detection fails."""
    df = pd.read_csv(filepath, dtype=str, nrows=0)
    return [c.strip() for c in df.columns]


def detect_columns(headers):
    """Auto-detect column roles by common bank header aliases."""
    return {
        "date":   _find_col(headers, DATE_COLS),
        "desc":   _find_col(headers, DESC_COLS),
        "amount": _find_col(headers, AMOUNT_COLS),
        "debit":  _find_col(headers, DEBIT_COLS),
        "credit": _find_col(headers, CREDIT_COLS),
        "type":   _find_col(headers, TYPE_COLS),
    }


def parse_csv(filepath, account_id, flip_signs=False, mapping=None):
    """
    Parse a bank/credit CSV. Returns (rows, stats) where:
      rows  — list of dicts ready for models.transaction.bulk_insert
      stats — dict: total, rule_matched, unmatched, batch_id, headers, columns

    flip_signs: negate all amounts (accounts.flip_amount_signs) — card issuers
    disagree on whether a charge is positive or negative.
    mapping: optional explicit column mapping {"date","desc","amount","debit","credit"}
    (from accounts.csv_mapping or the import preview); overrides auto-detection
    for the keys it provides.
    """
    # index_col=False: rows with a trailing comma (Citi checking) otherwise make
    # pandas treat the first column as an index, shifting every column left.
    df = pd.read_csv(filepath, dtype=str, skip_blank_lines=True, index_col=False)
    df.columns = df.columns.str.strip()
    rules = load_rules()

    headers = list(df.columns)
    cols = detect_columns(headers)
    if mapping:
        cols.update({k: v for k, v in mapping.items() if v and v in headers})

    date_col, desc_col = cols["date"], cols["desc"]
    amount_col, debit_col, credit_col = cols["amount"], cols["debit"], cols["credit"]
    type_col = cols["type"]

    if not date_col or not desc_col:
        raise ValueError(
            f"Could not detect date/description columns. Found: {headers}"
        )

    batch_id = str(uuid.uuid4())
    rows = []
    rule_matched = 0

    for _, raw_row in df.iterrows():
        date_str = _parse_date(raw_row[date_col])
        description = str(raw_row[desc_col]).strip()

        # Resolve amount
        if amount_col and type_col:
            # Single unsigned amount column + a separate Credit/Debit type
            # column (e.g. Capital One: "Transaction Amount" + "Transaction Type").
            raw_amount = _parse_amount(raw_row[amount_col])
            amount = abs(raw_amount) if raw_amount is not None else None
            if amount is not None and str(raw_row[type_col]).strip().lower().startswith(("debit", "withdrawal", "dr")):
                amount = -amount
        elif amount_col:
            amount = _parse_amount(raw_row[amount_col])
        elif debit_col and credit_col:
            # Empty cells parse to None (pandas turns blanks into NaN) — treat as 0.
            debit  = _parse_amount(raw_row.get(debit_col))  or 0.0
            credit = _parse_amount(raw_row.get(credit_col)) or 0.0
            if debit == 0.0 and credit == 0.0:
                continue
            # Debits are outflows (negative), credits are inflows (positive).
            # abs() on both: some issuers (Citi) report credits as negative values.
            amount = abs(credit) - abs(debit)
        else:
            raise ValueError("Could not detect amount column(s).")

        if not date_str or not description or amount is None:
            continue

        if flip_signs:
            amount = -amount

        category = apply_rules(description, rules)
        if category:
            rule_matched += 1

        rows.append({
            "account_id":      account_id,
            "date":            date_str,
            "description":     description,
            "amount":          amount,
            "currency":        "USD",
            "category":        category,
            "category_source": "rule" if category else None,
            "raw_csv_row":     json.dumps(dict(raw_row)),
            "import_batch_id": batch_id,
        })

    stats = {
        "total":         len(rows),
        "rule_matched":  rule_matched,
        "unmatched":     len(rows) - rule_matched,
        "skipped":       len(df) - len(rows),
        "batch_id":      batch_id,
        "headers":       headers,
        "columns":       cols,
    }
    return rows, stats


def _parse_date(val):
    if not val or str(val).strip().lower() in ("", "nan", "none"):
        return None
    val = str(val).strip()
    # %m-%d-%Y: Citi checking exports use dashes (e.g. 06-09-2026)
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%m-%d-%Y", "%d/%m/%Y", "%b %d, %Y", "%d-%b-%Y"):
        try:
            from datetime import datetime
            return datetime.strptime(val, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def _parse_amount(val):
    if val is None:
        return None
    s = str(val).strip().replace(",", "").replace("$", "").replace(" ", "")
    if not s or s.lower() in ("nan", "none", "-"):
        return None
    try:
        return float(s)
    except ValueError:
        return None
