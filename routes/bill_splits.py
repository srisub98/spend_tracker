from flask import Blueprint, render_template, request, redirect, url_for, flash
import models.bill_split as split_model

bp = Blueprint("splits", __name__, url_prefix="/splits")


@bp.route("/")
def index():
    split_model.backfill_people()   # link any legacy name-only participants
    outings    = split_model.get_all_outings()
    total_owed = split_model.get_total_owed()
    return render_template("splits/index.html", outings=outings, total_owed=total_owed,
                           receivable=split_model.total_receivable())


@bp.route("/people")
def people():
    split_model.backfill_people()
    return render_template("splits/people.html",
                           ledger=split_model.person_ledger(),
                           receivable=split_model.total_receivable())


@bp.route("/people/<int:person_id>/settle", methods=["POST"])
def settle(person_id):
    n = split_model.settle_person(person_id)
    flash(f"Settled — {n} item(s) marked paid." if n else "Nothing to settle.")
    return redirect(url_for("splits.people"))


@bp.route("/people/<int:person_id>/venmo", methods=["POST"])
def set_venmo(person_id):
    split_model.update_person(person_id, venmo_handle=request.form.get("venmo_handle", "").strip())
    return redirect(url_for("splits.people"))


@bp.route("/new", methods=["POST"])
def new():
    title       = request.form["title"].strip()
    outing_date = request.form["outing_date"]
    notes       = request.form.get("notes", "").strip()
    outing_id   = split_model.create_outing(title, outing_date, notes)
    return redirect(url_for("splits.detail", outing_id=outing_id))


@bp.route("/<int:outing_id>")
def detail(outing_id):
    outing  = split_model.get_outing(outing_id)
    if not outing:
        flash("Outing not found.", "error")
        return redirect(url_for("splits.index"))
    summary = split_model.get_outing_summary(outing_id)
    return render_template("splits/detail.html", outing=outing, summary=summary)


@bp.route("/<int:outing_id>/item", methods=["POST"])
def add_item(outing_id):
    try:
        total_amount = float(request.form["total_amount"])
        split_count  = int(request.form.get("split_count", 2))
        split_model.add_line_item(
            outing_id,
            request.form["description"].strip(),
            total_amount,
            paid_by_me=1,
            split_count=split_count,
        )
    except (ValueError, KeyError) as e:
        flash(f"Invalid item: {e}", "error")
    return redirect(url_for("splits.detail", outing_id=outing_id))


@bp.route("/<int:outing_id>/participant", methods=["POST"])
def add_participant(outing_id):
    name = request.form["name"].strip()
    if name:
        split_model.add_participant(outing_id, name)
    return redirect(url_for("splits.detail", outing_id=outing_id))


@bp.route("/<int:outing_id>/participant/<int:participant_id>/paid", methods=["POST"])
def mark_paid(outing_id, participant_id):
    split_model.mark_paid(participant_id)
    return redirect(url_for("splits.detail", outing_id=outing_id))


@bp.route("/<int:outing_id>/participant/<int:participant_id>/unpaid", methods=["POST"])
def mark_unpaid(outing_id, participant_id):
    split_model.mark_unpaid(participant_id)
    return redirect(url_for("splits.detail", outing_id=outing_id))


@bp.route("/<int:outing_id>/item/<int:item_id>/delete", methods=["POST"])
def delete_item(outing_id, item_id):
    split_model.delete_line_item(item_id)
    return redirect(url_for("splits.detail", outing_id=outing_id))


@bp.route("/<int:outing_id>/delete", methods=["POST"])
def delete(outing_id):
    split_model.delete_outing(outing_id)
    flash("Outing deleted.")
    return redirect(url_for("splits.index"))
