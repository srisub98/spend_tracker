"""
Categorization rules. The live registry is the `rules` DB table (editable in-app from
Phase 3 onward); SEED_RULES below only populates it on first init.

Matching: rules are checked in (priority ASC, id ASC) order; first match wins.
'substring' patterns are case-insensitive substring matches, 'regex' patterns are
case-insensitive regexes. Group order in SEED_RULES matters — e.g. "uber eats" (Food)
must be checked before "uber" (Car), so Food's group precedes Car's.
"""

import re
from models.rule import get_active

# (list_of_substring_patterns, category) — group index becomes the priority.
# Categories must exist in database/seed_data.py CATEGORY_SEED.
SEED_RULES = [
    # Income
    (["direct dep", "directdep", "payroll", "salary", "gusto", "adp", "paychex"], "Paycheck"),
    (["dividend", "interest earned", "interest paid", "int payment"], "Interest"),

    # Transfers (neutral — excluded from spend and income)
    # "payment - thank you" covers Amex "MOBILE PAYMENT - THANK YOU";
    # "american expr ach pmt" is the checking-side of Amex card payments.
    (["zelle", "venmo", "paypal", "cash app", "cashapp", "transfer", "wire",
      "autopay", "payment thank you", "payment - thank you", "online payment",
      "american expr ach pmt"], "Transfers"),

    # Groceries
    (["whole foods", "wholefds", "trader joe", "safeway", "kroger", "wegmans", "sprouts",
      "publix", "aldi", "costco", "bj's wholesale", "stop & shop", "market basket",
      "harris teeter", "h-e-b", "giant food", "meijer", "food lion"], "Groceries"),

    # Food (restaurants + delivery) — before Car so "uber eats" wins over "uber".
    # "doordas" (not "doordash"): card descriptors truncate, e.g. "BT*DD *DOORDASAN FRANCISCO"
    # "tst*" is the Toast POS prefix used by many independent restaurants/bars.
    (["restaurant", "doordas", "grubhub", "ubereats", "uber eats", "seamless",
      "postmates", "chick-fil-a", "mcdonald", "starbucks", "dunkin", "chipotle",
      "domino", "pizza", "sushi", "cafe ", "diner", "grill ", "bistro", "tavern",
      "eatery", "taco bell", "wendy's", "subway ", "panera", "shake shack", "tst*"], "Food"),

    # Fitness
    (["equinox", "planet fitness", "24 hour fitness", "crunch fitness", "classpass",
      "strava", "peloton", "orangetheory", "barry's", "soulcycle", "gym "], "Fitness"),

    # Car — local transport, gas, parking, insurance
    (["uber", "lyft", "waymo", "mta ", "metro card", "metrocard", "transit",
      "parkingmeter", "parking ", "easypark", "e-zpass", "ezpass", "toll",
      "shell ", "chevron", "exxon", "mobil ", "arco", "valero", "gas station",
      "car insurance", "geico", "jiffy lube", "autozone", "car wash", "dmv"], "Car"),

    # Travel — flights, trains, lodging
    (["airbnb", "vrbo", "hotel", "marriott", "hilton", "hyatt", "expedia",
      "booking.com", "priceline", "kayak", "amtrak", "greyhound", "jetblue",
      "delta air", "united air", "american air", "southwest", "spirit air",
      "frontier air", "alaska air"], "Travel"),

    # Entertainment — streaming + events (before Misc shopping so "amazon prime" wins over "amazon")
    (["netflix", "spotify", "hulu", "disney+", "youtube premium", "hbo", "max.com",
      "peacock", "paramount+", "amazon prime", "prime video", "ticketmaster", "stubhub",
      "eventbrite", "cinema", "amc ", "regal ", "fandango", "concert", "theater",
      "museum", "live nation", "playstation", "nintendo", "topgolf"], "Entertainment"),

    # Misc — software/tools subscriptions ("apple.com/bil" not "bill": Apple's
    # card descriptor truncates, e.g. "APPLE.COM/BILINTERNET CHARGE")
    (["apple.com/bil", "apple one", "microsoft 365", "adobe", "dropbox", "icloud",
      "google one", "notion", "chatgpt", "openai", "anthropic", "github", "figma",
      "slack", "zoom"], "Misc"),

    # Home — furniture/improvement
    (["home depot", "lowe's", "ikea", "wayfair", "bed bath", "container store",
      "ace hardware"], "Home"),

    # Clothes
    (["nordstrom", "macy's", "gap ", "h&m", "zara", "uniqlo", "zappos", "old navy",
      "banana republic", "lululemon", "nike.com", "adidas"], "Clothes"),

    # Misc — general shopping
    (["amazon", "amzn", "target", "walmart", "best buy", "etsy", "ebay", "chewy"], "Misc"),

    # Health
    (["cvs pharmacy", "walgreens", "rite aid", "pharmacy", "doctor", "dentist",
      "medical", "hospital", "clinic", "urgent care", "lab corp", "quest diag",
      "optum", "cigna", "aetna", "blue cross", "kaiser"], "Health"),

    # Rent + Utilities (rent, power, internet, phone)
    (["rent ", "mortgage", "landlord", "property mgmt", "electric", "gas bill",
      "water bill", "utility", "pg&e", "pgande", "comcast", "xfinity", "verizon",
      "at&t", "t-mobile", "tmobile", "spectrum", "internet", "phone bill"], "Rent + Utilities"),

    # Donations
    (["donation", "gofundme", "red cross", "charity"], "Donations"),

    # Misc — personal care
    (["salon", "barbershop", "haircut", "spa ", "massage", "nail ", "beauty"], "Misc"),

    # Investments — money moved into brokerage (drives FCF)
    (["robinhood", "fidelity", "schwab", "vanguard", "etrade", "td ameritrade",
      "coinbase", "kraken", "wealthfront", "betterment", "fundrise"], "Investments"),

    # Misc — fees
    (["late fee", "overdraft", "service fee", "annual fee", "interest charge",
      "foreign transaction", "atm fee"], "Misc"),

    # Misc — cash
    (["cash withdrawal", "atm withdrawal"], "Misc"),
]


def seed_rows():
    """Flatten SEED_RULES into (pattern, match_type, category, priority) rows."""
    rows = []
    for group_idx, (patterns, category) in enumerate(SEED_RULES):
        priority = (group_idx + 1) * 10
        for pattern in patterns:
            rows.append((pattern, "substring", category, priority))
    return rows


def load_rules():
    """Load active rules from the DB, compiled for fast matching. Call once per import."""
    compiled = []
    for r in get_active():
        if r["match_type"] == "regex":
            try:
                compiled.append(("regex", re.compile(r["pattern"], re.IGNORECASE), r["category"]))
            except re.error:
                continue
        else:
            compiled.append(("substring", r["pattern"].lower(), r["category"]))
    return compiled


def _longest_common_substring(a: str, b: str) -> str:
    m, n = len(a), len(b)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    best_len, best_end = 0, 0
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if a[i - 1] == b[j - 1]:
                dp[i][j] = dp[i - 1][j - 1] + 1
                if dp[i][j] > best_len:
                    best_len = dp[i][j]
                    best_end = i
    return a[best_end - best_len:best_end]


def suggest_pattern(descriptions: list[str], min_len: int = 4) -> str | None:
    """Find a substring shared across all of `descriptions` long enough to be a
    useful rule pattern (e.g. mass-categorizing several "TST* ..." rows
    suggests "tst*"). Returns None if nothing common enough is found."""
    unique = list(dict.fromkeys(d.upper() for d in descriptions))
    if len(unique) < 2:
        return None
    common = unique[0]
    for d in unique[1:]:
        common = _longest_common_substring(common, d)
        if len(common.strip()) < min_len:
            return None
    common = common.strip(" -*:#")
    return common.lower() if len(common) >= min_len else None


def apply_rules(description: str, rules) -> str | None:
    """Return the first matching category, or None. `rules` comes from load_rules()."""
    desc = description.lower()
    for match_type, pattern, category in rules:
        if match_type == "substring":
            if pattern in desc:
                return category
        elif pattern.search(description):
            return category
    return None
