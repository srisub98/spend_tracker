"""
Seed data for the categories table. Names match Sri's Google Sheet (docs/PRD.md §4)
so bootstrapped history and live transactions pivot in the same table.
Inserted by init_db() only when the categories table is empty.
"""

# (name, kind, sort_order)
CATEGORY_SEED = [
    # Expenses — sheet order
    ("Rent + Utilities", "expense", 10),
    ("Home",             "expense", 20),
    ("Groceries",        "expense", 30),
    ("Food",             "expense", 40),
    ("Clothes",          "expense", 50),
    ("Entertainment",    "expense", 60),
    ("Fitness",          "expense", 70),
    ("Donations",        "expense", 80),
    ("Misc",             "expense", 90),
    ("Travel",           "expense", 100),
    ("Car",              "expense", 110),
    ("Health",           "expense", 120),
    # Income
    ("Paycheck",         "income", 200),
    ("RSU Vest",         "income", 210),
    ("Interest",         "income", 220),
    ("Other Income",     "income", 230),
    # Neutral / investment
    ("Transfers",        "transfer", 300),
    ("Investments",      "investment", 310),
]
