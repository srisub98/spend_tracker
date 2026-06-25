import os
from flask import Blueprint, render_template, redirect, url_for, flash
from services.excel_exporter import export_excel
from services.html_exporter import export_html
import config

bp = Blueprint("exports", __name__, url_prefix="/export")


@bp.route("/")
def index():
    files = []
    if os.path.exists(config.OUTPUT_FOLDER):
        files = sorted(os.listdir(config.OUTPUT_FOLDER), reverse=True)
    return render_template("export/index.html", files=files)


@bp.route("/excel", methods=["POST"])
def excel():
    try:
        path = export_excel()
        flash(f"Excel exported: {os.path.basename(path)}")
    except Exception as e:
        flash(f"Export failed: {e}", "error")
    return redirect(url_for("exports.index"))


@bp.route("/html", methods=["POST"])
def html():
    try:
        path = export_html()
        flash(f"HTML dashboard exported: {os.path.basename(path)}")
    except Exception as e:
        flash(f"Export failed: {e}", "error")
    return redirect(url_for("exports.index"))
