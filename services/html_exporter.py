import os
import json
from datetime import datetime
import config
from database.db import get_db
import models.aggregates as agg
import models.net_worth as nw_model

# Chart.js is embedded inline so the exported file works fully offline
# (e.g. opened from iCloud Drive on a phone). Vendored copy: static/js/.
_CHARTJS_PATH = os.path.join(os.path.dirname(__file__), "..", "static", "js",
                             "chart.umd.min.js")

CLASS_COLORS = {"stocks": "#007aff", "cash": "#30d158",
                "retirement": "#af52de", "other": "#ff9f0a"}


def _chartjs_source():
    with open(_CHARTJS_PATH) as f:
        return f.read()


def _get_data():
    db = get_db()
    year = datetime.now().year
    d = agg.build_year_dashboard(year)
    dates, class_series = nw_model.get_class_series()
    grid = nw_model.get_year_grid(year)

    splits_rows = db.execute(
        """SELECT op.name, SUM(oli.per_person_amount) as owed
           FROM outing_participants op
           JOIN outing_line_items oli ON oli.outing_id=op.outing_id AND oli.paid_by_me=1
           WHERE op.is_paid=0
           GROUP BY op.name ORDER BY owed DESC"""
    ).fetchall()

    nw_rows = db.execute(
        "SELECT snapshot_date, net_worth FROM net_worth_snapshots "
        "ORDER BY snapshot_date ASC").fetchall()

    return {
        "year": year,
        "dash": d,
        "class_dates": dates,
        "class_series": class_series,
        "grid": grid,
        "splits_owed": [dict(r) for r in splits_rows],
        "current_net_worth": nw_rows[-1]["net_worth"] if nw_rows else None,
        "generated_at": datetime.now().strftime("%B %d, %Y %H:%M"),
    }


def export_html():
    os.makedirs(config.OUTPUT_FOLDER, exist_ok=True)
    filename = f"dashboard_{datetime.now().strftime('%Y%m%d_%H%M')}.html"
    path = os.path.join(config.OUTPUT_FOLDER, filename)

    html = _render(_get_data())
    with open(path, "w") as f:
        f.write(html)
    return path


def _fmt(val):
    if val is None:
        return "N/A"
    return f"${val:,.0f}"


def _grid_table(grid):
    if not grid["months"]:
        return "<p>No snapshots this year.</p>"
    head = "<tr><th>Account</th>" + "".join(
        f"<th class='num'>{m:02d}</th>" for m in grid["months"]) + "</tr>"
    body = ""
    for a in grid["accounts"]:
        cells = "".join(
            f"<td class='num'>{a['by_month'][m]:,.0f}</td>" if m in a["by_month"]
            else "<td class='num'>—</td>" for m in grid["months"])
        body += f"<tr><td>{a['name']}</td>{cells}</tr>"
    nw = "".join(f"<td class='num'><strong>{grid['net_worth'].get(m, 0):,.0f}</strong></td>"
                 for m in grid["months"])
    body += f"<tr><td><strong>Net Worth</strong></td>{nw}</tr>"
    return f"<div style='overflow-x:auto'><table>{head}{body}</table></div>"


def _render(d):
    dash = d["dash"]
    months3 = [m[:3] for m in dash["months"]]
    class_datasets = json.dumps([
        {"label": c.title(), "data": d["class_series"][c],
         "backgroundColor": CLASS_COLORS[c]}
        for c in nw_model.CLASS_ORDER])
    cat_rows = [(r["name"], r["total"]) for r in dash["expense_rows"] if r["total"]]

    splits_rows = "".join(
        f"<tr><td>{r['name']}</td><td>${r['owed']:,.2f}</td></tr>"
        for r in d["splits_owed"]
    ) or "<tr><td colspan='2'>All clear!</td></tr>"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Finance Dashboard</title>
<script>{_chartjs_source()}</script>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
         background: #f5f5f7; margin: 0; padding: 16px; color: #1d1d1f; }}
  h1   {{ font-size: 1.6rem; margin-bottom: 4px; }}
  .sub {{ color: #6e6e73; font-size: 0.85rem; margin-bottom: 20px; }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 12px; margin-bottom: 20px; }}
  .card {{ background: #fff; border-radius: 12px; padding: 16px; box-shadow: 0 1px 4px rgba(0,0,0,.08); }}
  .card .label {{ font-size: 0.75rem; color: #6e6e73; text-transform: uppercase; letter-spacing: .05em; }}
  .card .value {{ font-size: 1.4rem; font-weight: 600; margin-top: 4px; }}
  .chart-wrap {{ background: #fff; border-radius: 12px; padding: 16px; box-shadow: 0 1px 4px rgba(0,0,0,.08); margin-bottom: 16px; }}
  .chart-wrap h2 {{ font-size: 1rem; margin: 0 0 12px; }}
  table {{ width: 100%; border-collapse: collapse; }}
  th, td {{ text-align: left; padding: 6px 8px; border-bottom: 1px solid #f0f0f0; font-size: 0.85rem; white-space: nowrap; }}
  th {{ color: #6e6e73; font-weight: 500; }}
  td.num, th.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
  .positive {{ color: #30d158; }} .negative {{ color: #ff3b30; }}
</style>
</head>
<body>
<h1>Finance Dashboard {d["year"]}</h1>
<p class="sub">Generated {d["generated_at"]} — fully offline (Chart.js embedded)</p>

<div class="grid">
  <div class="card">
    <div class="label">Net Worth</div>
    <div class="value positive">{_fmt(d["current_net_worth"])}</div>
  </div>
  <div class="card">
    <div class="label">Income {d["year"]}</div>
    <div class="value positive">{_fmt(dash["ytd"]["income"])}</div>
  </div>
  <div class="card">
    <div class="label">Expenses {d["year"]}</div>
    <div class="value negative">{_fmt(dash["ytd"]["expenses"])}</div>
  </div>
  <div class="card">
    <div class="label">FCF {d["year"]}</div>
    <div class="value">{_fmt(dash["ytd"]["fcf"])}</div>
  </div>
  <div class="card">
    <div class="label">Owed to You</div>
    <div class="value">{_fmt(sum(r["owed"] for r in d["splits_owed"]))}</div>
  </div>
</div>

<div class="chart-wrap">
  <h2>Net Worth by Asset Class</h2>
  <canvas id="nwChart" height="90"></canvas>
</div>

<div class="chart-wrap">
  <h2>Income vs Expenses {d["year"]}</h2>
  <canvas id="moChart" height="80"></canvas>
</div>

<div class="chart-wrap">
  <h2>Spending by Category {d["year"]}</h2>
  <canvas id="catChart" height="100"></canvas>
</div>

<div class="chart-wrap">
  <h2>Accounts by Month {d["year"]}</h2>
  {_grid_table(d["grid"])}
</div>

<div class="chart-wrap">
  <h2>Who Owes You</h2>
  <table>
    <tr><th>Person</th><th>Amount</th></tr>
    {splits_rows}
  </table>
</div>

<script>
const money = v => '$' + v.toLocaleString();

new Chart(document.getElementById('nwChart'), {{
  type: 'bar',
  data: {{ labels: {json.dumps(d["class_dates"])}, datasets: {class_datasets} }},
  options: {{ scales: {{ x: {{ stacked: true }}, y: {{ stacked: true,
    ticks: {{ callback: money }} }} }} }}
}});

new Chart(document.getElementById('moChart'), {{
  data: {{ labels: {json.dumps(months3)}, datasets: [
    {{ type: 'bar', label: 'Income',   data: {json.dumps(dash["income_total"])},  backgroundColor: 'rgba(48,209,88,.7)' }},
    {{ type: 'bar', label: 'Expenses', data: {json.dumps(dash["expense_total"])}, backgroundColor: 'rgba(255,59,48,.6)' }},
    {{ type: 'line', label: 'Net',     data: {json.dumps(dash["net"])}, borderColor: '#007aff', tension: .3 }}
  ] }},
  options: {{ scales: {{ y: {{ ticks: {{ callback: money }} }} }} }}
}});

new Chart(document.getElementById('catChart'), {{
  type: 'bar',
  data: {{ labels: {json.dumps([n for n, _ in cat_rows])},
           datasets: [{{ label: 'Spent', data: {json.dumps([round(t, 2) for _, t in cat_rows])},
                         backgroundColor: '#30d158' }}] }},
  options: {{ indexAxis: 'y', plugins: {{ legend: {{ display: false }} }},
    scales: {{ x: {{ ticks: {{ callback: money }} }} }} }}
}});
</script>
</body>
</html>"""
