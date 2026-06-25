import re
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
import models.rule as rule_model
import models.category as category_model
from services.rules import load_rules, apply_rules
from database.db import get_db

bp = Blueprint("rules", __name__, url_prefix="/rules")


@bp.route("/")
def index():
    edit_id = request.args.get("edit")
    edit_rule = None
    if edit_id:
        edit_rule = next((r for r in rule_model.get_all() if str(r["id"]) == edit_id), None)
    return render_template(
        "rules/index.html",
        rules=rule_model.get_all(),
        categories=category_model.get_all(),
        edit_rule=edit_rule,
        # Prefill support for "make this a rule" links from the review page
        prefill_pattern=request.args.get("pattern", ""),
        prefill_category=request.args.get("category", ""),
    )


def _validated_form(form):
    pattern = form.get("pattern", "").strip()
    match_type = form.get("match_type", "substring")
    category = form.get("category", "")
    try:
        priority = int(form.get("priority", 100))
    except ValueError:
        priority = 100
    if not pattern:
        raise ValueError("Pattern is required.")
    if match_type not in ("substring", "regex"):
        raise ValueError("Bad match type.")
    if match_type == "regex":
        try:
            re.compile(pattern)
        except re.error as e:
            raise ValueError(f"Invalid regex: {e}")
    if category not in category_model.get_names():
        raise ValueError("Pick a valid category.")
    return pattern, match_type, category, priority


@bp.route("/", methods=["POST"])
def create():
    try:
        pattern, match_type, category, priority = _validated_form(request.form)
    except ValueError as e:
        flash(str(e), "error")
        return redirect(url_for("rules.index"))
    rule_model.create(pattern, category, match_type, priority)
    flash(f'Rule added: "{pattern}" → {category}.')
    return redirect(url_for("rules.index"))


@bp.route("/<int:rule_id>/edit", methods=["POST"])
def edit(rule_id):
    try:
        pattern, match_type, category, priority = _validated_form(request.form)
    except ValueError as e:
        flash(str(e), "error")
        return redirect(url_for("rules.index", edit=rule_id))
    active = 1 if request.form.get("active") else 0
    rule_model.update(rule_id, pattern, category, match_type, priority, active)
    flash("Rule updated.")
    return redirect(url_for("rules.index"))


@bp.route("/<int:rule_id>/toggle", methods=["POST"])
def toggle(rule_id):
    db = get_db()
    db.execute("UPDATE rules SET active = 1 - active WHERE id=?", (rule_id,))
    db.commit()
    return redirect(url_for("rules.index"))


@bp.route("/<int:rule_id>/delete", methods=["POST"])
def delete(rule_id):
    rule_model.delete(rule_id)
    flash("Rule deleted.")
    return redirect(url_for("rules.index"))


@bp.route("/test")
def test():
    """Dry-run a pattern against all existing transactions (nothing is changed)."""
    pattern = request.args.get("pattern", "").strip()
    match_type = request.args.get("match_type", "substring")
    if not pattern:
        return jsonify(count=0, sample=[])

    if match_type == "regex":
        try:
            rx = re.compile(pattern, re.IGNORECASE)
        except re.error as e:
            return jsonify(error=f"Invalid regex: {e}"), 400
        match = lambda d: rx.search(d) is not None
    else:
        needle = pattern.lower()
        match = lambda d: needle in d.lower()

    txs = get_db().execute(
        "SELECT date, description, amount, category FROM transactions ORDER BY date DESC"
    ).fetchall()
    hits = [t for t in txs if match(t["description"])]
    return jsonify(
        count=len(hits),
        sample=[dict(t) for t in hits[:8]],
    )


@bp.route("/reapply", methods=["POST"])
def reapply():
    """Re-run active rules over every transaction whose category wasn't set by
    the user. User-corrected rows are never touched; rows no rule matches keep
    their current (e.g. Claude-assigned) category."""
    rules = load_rules()
    db = get_db()
    txs = db.execute(
        "SELECT id, description, category, category_source FROM transactions "
        "WHERE category_source IS NULL OR category_source IN ('rule','claude')"
    ).fetchall()
    changed = 0
    for t in txs:
        cat = apply_rules(t["description"], rules)
        if cat and (cat != t["category"] or t["category_source"] != "rule"):
            db.execute(
                "UPDATE transactions SET category=?, category_source='rule' WHERE id=?",
                (cat, t["id"]),
            )
            changed += 1
    db.commit()
    flash(f"Re-applied rules: {changed} of {len(txs)} eligible transactions updated. "
          "User-set categories were not touched.")
    return redirect(url_for("rules.index"))
