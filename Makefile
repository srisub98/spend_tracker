# Finance Tracker — common tasks. Run `make` to list targets.

VENV   := .venv
PYTHON := $(VENV)/bin/python
PIP    := $(VENV)/bin/pip

.DEFAULT_GOAL := help

.PHONY: help install run bootstrap bootstrap-reset db-shell reset-db export-dir clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

$(VENV)/bin/python:
	python3 -m venv $(VENV)

install: $(VENV)/bin/python ## Create .venv and install dependencies
	$(PIP) install -q --upgrade pip
	$(PIP) install -q -r requirements.txt
	@echo "Installed. Copy .env.example to .env if you haven't."

run: ## Start the Flask app (reads PORT from .env, default 5000)
	$(PYTHON) app.py

bootstrap: ## Import historical data from data/bootstrap/expenses.xlsx
	$(PYTHON) scripts/bootstrap_from_sheet.py

bootstrap-reset: ## Wipe previously bootstrapped sheet data and reimport
	$(PYTHON) scripts/bootstrap_from_sheet.py --reset

db-shell: ## Open a sqlite3 shell on the database
	sqlite3 data/finance.db

reset-db: ## Delete the database (recreates + reseeds on next run) — DESTRUCTIVE
	@read -p "Delete data/finance.db? [y/N] " ans && [ "$$ans" = "y" ] && rm -f data/finance.db && echo "Deleted." || echo "Aborted."

clean: ## Remove venv and python caches
	rm -rf $(VENV) **/__pycache__ __pycache__
