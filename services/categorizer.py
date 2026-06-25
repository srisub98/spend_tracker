import json
import logging
import anthropic
import config
import models.category as category_model

BATCH_SIZE = 50
logger = logging.getLogger(__name__)


def categorize_transactions(transactions):
    """
    transactions: iterable of rows/dicts with at least 'id' and 'description'.
    Only processes rows where category is None (no rule matched).
    Returns (pairs, errors):
      pairs  — list of (id, category) for bulk_update_category
      errors — list of user-facing error strings (empty on full success)
    """
    uncategorized = [t for t in transactions if not t["category"]]
    if not uncategorized:
        return [], []

    if not config.ANTHROPIC_API_KEY:
        return [], [
            f"{len(uncategorized)} transactions need categories, but no ANTHROPIC_API_KEY "
            "is configured — assign them manually on the review page."
        ]

    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    valid_categories = category_model.get_names()
    results = []
    errors = []

    for i in range(0, len(uncategorized), BATCH_SIZE):
        batch = uncategorized[i:i + BATCH_SIZE]
        try:
            results.extend(_call_claude(client, batch, valid_categories))
        except Exception as e:
            logger.exception("Claude categorization failed")
            errors.append(
                f"Claude categorization failed ({e.__class__.__name__}: {e}) — "
                f"{len(uncategorized) - i} transactions left for manual review."
            )
            break  # same error would likely hit every remaining batch

    return results, errors


def _call_claude(client, batch, valid_categories):
    categories_str = ", ".join(f'"{c}"' for c in valid_categories)
    lines = "\n".join(f"{j+1}. {t['description']}" for j, t in enumerate(batch))

    prompt = f"""Categorize each financial transaction below into exactly one of these categories:
{categories_str}

Return a JSON array of strings — one category per transaction, in the same order.
No explanation. Only the JSON array.

Transactions:
{lines}"""

    message = client.messages.create(
        model=config.CLAUDE_MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = message.content[0].text.strip()
    # Strip markdown code fences if present
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    categories = json.loads(raw.strip())
    if not isinstance(categories, list) or len(categories) != len(batch):
        raise ValueError(
            f"expected a JSON array of {len(batch)} categories, got {len(categories) if isinstance(categories, list) else type(categories).__name__}"
        )

    valid = set(valid_categories)
    # Drop hallucinated category names rather than polluting the table
    return [(t["id"], cat) for t, cat in zip(batch, categories) if cat in valid]
