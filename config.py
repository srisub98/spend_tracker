import os
from dotenv import load_dotenv

load_dotenv()

DB_PATH = os.getenv("DB_PATH", "data/finance.db")
OUTPUT_FOLDER = os.getenv("OUTPUT_FOLDER", "data/exports")
UPLOAD_FOLDER = os.getenv("UPLOAD_FOLDER", "data/uploads")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")

# macOS AirPlay Receiver squats on port 5000 — set PORT=5001 in .env if needed.
PORT = int(os.getenv("PORT", "5000"))

# Schwab Trader API (free individual developer app — developer.schwab.com, PRD Phase 4b).
# The callback URL must EXACTLY match the one registered on the Schwab app.
SCHWAB_APP_KEY = os.getenv("SCHWAB_APP_KEY", "")
SCHWAB_APP_SECRET = os.getenv("SCHWAB_APP_SECRET", "")
SCHWAB_CALLBACK_URL = os.getenv("SCHWAB_CALLBACK_URL", "https://127.0.0.1")

# Hard cutover between bootstrapped sheet history and live transaction data (PRD §5).
# Months < LIVE_START_MONTH read from monthly_summaries; months >= read from transactions.
LIVE_START_MONTH = os.getenv("LIVE_START_MONTH", "2026-06")

# Categories now live in the `categories` DB table (seeded from database/seed_data.py).
# Use models.category.get_names() instead of a config constant.
