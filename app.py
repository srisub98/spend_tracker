import os
from flask import Flask, redirect, url_for
from database.db import init_db
from routes import (transactions, accounts, net_worth, bill_splits, exports,
                    dashboard, rules, life, investments, insights, plaid)

app = Flask(__name__)
app.secret_key = os.urandom(24)

app.register_blueprint(dashboard.bp)
app.register_blueprint(transactions.bp)
app.register_blueprint(rules.bp)
app.register_blueprint(life.bp)
app.register_blueprint(accounts.bp)
app.register_blueprint(plaid.bp)
app.register_blueprint(net_worth.bp)
app.register_blueprint(investments.bp)
app.register_blueprint(insights.bp)
app.register_blueprint(bill_splits.bp)
app.register_blueprint(exports.bp)

@app.context_processor
def inject_globals():
    from datetime import date
    return {"fy_year": date.today().year}


@app.route("/")
def index():
    return redirect(url_for("dashboard.index"))

if __name__ == "__main__":
    import config
    init_db(app)
    os.makedirs("data/uploads", exist_ok=True)
    os.makedirs("data/exports", exist_ok=True)
    # Debug (and its auto-reloader) stay on for `make run`; the e2e harness sets
    # FLASK_DEBUG=0 so Playwright drives a single, stable server process.
    debug = os.environ.get("FLASK_DEBUG", "1") != "0"
    app.run(debug=debug, port=config.PORT, use_reloader=debug)
