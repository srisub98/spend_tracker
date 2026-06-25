"""Shared pytest fixtures.

Every DB-backed test runs against a fresh temp SQLite file and is hermetic:
ANTHROPIC_API_KEY is blanked so services/categorizer.py short-circuits (no
network). config.* values are read dynamically by the app, so monkeypatching
them here is enough to redirect the whole app at the temp paths.
"""
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = REPO_ROOT / "tests" / "fixtures"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import config  # noqa: E402


@pytest.fixture()
def fixtures_dir():
    return FIXTURES


@pytest.fixture()
def flask_app(tmp_path, monkeypatch):
    """Flask app bound to a fresh temp DB, seeded with demo accounts + the
    standard category/rule seeds."""
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setattr(config, "UPLOAD_FOLDER", str(tmp_path / "uploads"))
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "")

    from app import app
    from scripts.seed_test_db import seed_accounts

    seed_accounts()  # init_db (schema + seeds) + demo accounts, into the temp DB
    app.config.update(TESTING=True)
    return app


@pytest.fixture()
def client(flask_app):
    return flask_app.test_client()
