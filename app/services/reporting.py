"""
Post-transformation reporting: reconciliation summary, method note, a
Power BI-ready workbook (star-schema friendly) and a standalone,
downloadable analytics dashboard (HTML + Chart.js, no server required).

These satisfy the Hackfest "must-have participant outputs":
  1) Cleaned dataset (already produced by transformer.write_output)
  2) Data-quality issue log (already produced in jobs.py)
  3) Reconciliation summary               <- this module
  4) Short method note (AI use, assumptions, confidence) <- this module
Plus a Power BI-ready export and an interactive dashboard for demo readiness.
"""
import json
import csv
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.chart import BarChart, PieChart, Reference


PRIMARY = "1F3A93"
ACCENT = "315EFB"


def build_reconciliation(job, all_output, all_issues, input_rows, null_count):
    """Return a reconciliation dict + write it as both CSV and a formatted sheet."""
    issue_types = Counter(i["issue_type"] for i in all_issues)
    output_rows = len(all_output)
    removed = issue_types.get("NULL_ROW_REMOVED", 0) + issue_types.get("DUPLICATE_REMOVED", 0) + issue_types.get("AGGREGATE_ROW", 0)
    flagged = issue_types.get("INVALID_PERIOD", 0)
    recon = {
        "job_id": job["id"],
        "source_file": job["filename"],
        "input_rows": input_rows,
        "output_rows": output_rows,
        "rows_removed_null": issue_types.get("NULL_ROW_REMOVED", 0),
        "rows_removed_duplicate": issue_types.get("DUPLICATE_REMOVED", 0),
        "rows_removed_aggregate": issue_types.get("AGGREGATE_ROW", 0),
        "rows_flagged_invalid_period": flagged,
        "total_rows_removed_or_flagged": removed + flagged,
        "net_reconciliation_pct": round((output_rows / input_rows * 100), 2) if input_rows else 0.0,
        "null_cells_in_source": null_count,
        "total_issues_logged": len(all_issues),
        "issue_breakdown": dict(issue_types),
    }
    return recon


def write_reconciliation_csv(recon, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["Metric", "Value"])
        for k, v in recon.items():
            if k == "issue_breakdown":
                continue
            w.writerow([k, v])
        w.writerow([])
        w.writerow(["Issue type", "Count"])
        for k, v in recon.get("issue_breakdown", {}).items():
            w.writerow([k, v])


def write_method_note(report, recon, plan, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    assumptions = plan.get("assumptions") or []
    review = plan.get("review") or []
    transformations = plan.get("transformations") or []
    lines = [
        f"# Method Note — Job #{report['job_id']} ({report['filename']})",
        "",
        f"_Generated {datetime.now(timezone.utc).isoformat(timespec='seconds')}Z_",
        "",
        "## AI use",
        f"- Engine selected: **{report['engine']}** (Polars for files ≤ 1 GiB, PySpark above).",
        f"- Mapping/interpretation produced by the CSI LLM (`{report.get('llm_mode', 'CSI_LLM')}`).",
        f"- Reported model confidence: **{report.get('confidence', 0):.2f}**.",
        "- The LLM only proposes a transformation *plan* (column mapping, period strategy, matrix "
        "handling, confidence, review flags). All data movement — reading, cleaning, aggregation, "
        "writing — is executed by deterministic code so no AI output is written to client data directly.",
        "",
        "## Assumptions",
    ]
    lines += [f"- {a}" for a in assumptions] if assumptions else ["- None recorded by the model for this file."]
    lines += ["", "## Flagged for human review (low-confidence / ambiguous)"]
    lines += [f"- {r}" for r in review] if review else ["- No items were flagged for review."]
    lines += ["", "## Transformations applied"]
    if transformations:
        for t in transformations:
            rule = t.get("rule", "")
            cols = ", ".join(t.get("columns", []) or [])
            reason = t.get("reason", "")
            lines.append(f"- **{rule}** — columns: {cols or '—'} — {reason}")
    else:
        lines.append("- Standard cleaning only (trim, de-duplicate, blank-row removal, date/period normalization).")
    lines += [
        "",
        "## Reconciliation at a glance",
        f"- Input rows profiled: **{recon['input_rows']}**",
        f"- Output rows produced: **{recon['output_rows']}** ({recon['net_reconciliation_pct']}% of input)",
        f"- Rows removed (blank/duplicate/subtotal): **{recon['total_rows_removed_or_flagged']}**",
        f"- Issues logged: **{recon['total_issues_logged']}**",
        "",
        "## Guardrails honored",
    ]
    lines += [f"- {g}" for g in report.get("guardrails", [])]
    path.write_text("\n".join(lines), encoding="utf-8")


def write_powerbi_workbook(all_output, all_issues, recon, report, path: Path):
    """
    A clean, multi-sheet workbook ready to be used as a Power BI data source:
    Get Data -> Excel workbook -> select all three tables -> Load.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    wb = openpyxl.Workbook()

    # --- Cleaned_Data ---
    ws = wb.active
    ws.title = "Cleaned_Data"
    cols = sorted({k for row in all_output for k in row.keys() if not k.startswith("_")})
    header_fill = PatternFill("solid", fgColor=PRIMARY)
    header_font = Font(color="FFFFFF", bold=True)
    if cols:
        ws.append(cols)
        for row in all_output:
            ws.append([row.get(c) for c in cols])
    else:
        ws.append(["No rows produced"])
    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
    ws.freeze_panes = "A2"

    # --- Issue_Log ---
    ws2 = wb.create_sheet("Issue_Log")
    ws2.append(["source_row", "issue_type", "detail"])
    for cell in ws2[1]:
        cell.fill = header_fill
        cell.font = header_font
    for i in all_issues:
        ws2.append([i.get("source_row"), i.get("issue_type"), i.get("detail")])
    ws2.freeze_panes = "A2"

    # --- Reconciliation_Summary ---
    ws3 = wb.create_sheet("Reconciliation_Summary")
    ws3.append(["Metric", "Value"])
    for cell in ws3[1]:
        cell.fill = header_fill
        cell.font = header_font
    for k, v in recon.items():
        if k == "issue_breakdown":
            continue
        ws3.append([k, v])
    start = ws3.max_row + 2
    ws3.cell(row=start, column=1, value="Issue type").font = Font(bold=True)
    ws3.cell(row=start, column=2, value="Count").font = Font(bold=True)
    for j, (k, v) in enumerate(recon.get("issue_breakdown", {}).items(), start=start + 1):
        ws3.cell(row=j, column=1, value=k)
        ws3.cell(row=j, column=2, value=v)
    if recon.get("issue_breakdown"):
        chart = PieChart()
        chart.title = "Issues by type"
        data = Reference(ws3, min_col=2, min_row=start, max_row=j)
        cats = Reference(ws3, min_col=1, min_row=start + 1, max_row=j)
        chart.add_data(data, titles_from_data=True)
        chart.set_categories(cats)
        ws3.add_chart(chart, f"D{start}")

    # --- Run_Info (single row, good for a Power BI card/slicer) ---
    ws4 = wb.create_sheet("Run_Info")
    info_cols = ["job_id", "filename", "engine", "llm_mode", "confidence", "input_rows", "output_rows", "issues", "duration_seconds"]
    ws4.append(info_cols)
    for cell in ws4[1]:
        cell.fill = header_fill
        cell.font = header_font
    ws4.append([report.get(c) for c in info_cols])
    for col in ws4.columns:
        ws4.column_dimensions[col[0].column_letter].width = 16

    for sheet in (ws, ws2, ws3):
        for col_cells in sheet.columns:
            length = max((len(str(c.value)) if c.value is not None else 0) for c in col_cells)
            sheet.column_dimensions[col_cells[0].column_letter].width = min(max(length + 2, 10), 40)

    wb.save(path)


DASHBOARD_TEMPLATE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Job #{job_id} — Transformation Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.4/dist/chart.umd.min.js"></script>
<style>
:root{{--ink:#0f1524;--muted:#6b7590;--line:#e5e9f0;--primary:#5b6cff;--bg:#f4f6fb;--good:#17b978;--warn:#f5a524;--bad:#ef476f}}
*{{box-sizing:border-box}}
body{{margin:0;font-family:Inter,-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;background:var(--bg);color:var(--ink)}}
header{{background:radial-gradient(circle at 20% 0%,#1c2340,#0c1022 65%);color:#fff;padding:32px 40px}}
header .eyebrow{{font-size:12px;font-weight:800;letter-spacing:1.5px;opacity:.75;margin-bottom:8px}}
header h1{{margin:0 0 6px;font-size:26px}}
header p{{margin:0;opacity:.85;font-size:14px}}
main{{max-width:1180px;margin:-28px auto 60px;padding:0 24px}}
.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:16px;margin-bottom:24px}}
.card{{background:#fff;border:1px solid var(--line);border-radius:16px;padding:18px 20px;box-shadow:0 8px 30px rgba(28,38,61,.06)}}
.card .label{{font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;font-weight:700}}
.card .value{{font-size:28px;font-weight:800;margin-top:6px}}
.card .sub{{font-size:12px;color:var(--muted);margin-top:4px}}
.grid2{{display:grid;grid-template-columns:1.3fr 1fr;gap:20px;margin-bottom:20px}}
@media(max-width:900px){{.grid2{{grid-template-columns:1fr}}}}
.panel{{background:#fff;border:1px solid var(--line);border-radius:16px;padding:20px;box-shadow:0 8px 30px rgba(28,38,61,.05)}}
.panel h3{{margin:0 0 14px;font-size:15px}}
table{{width:100%;border-collapse:collapse;font-size:13px}}
th,td{{padding:8px 10px;text-align:left;border-bottom:1px solid var(--line)}}
th{{color:var(--muted);font-weight:700;text-transform:uppercase;font-size:11px}}
.badge{{display:inline-block;padding:3px 9px;border-radius:999px;font-size:11px;font-weight:700}}
.badge.good{{background:#e6f9f0;color:var(--good)}}
.badge.warn{{background:#fef3e0;color:var(--warn)}}
footer{{text-align:center;color:var(--muted);font-size:12px;padding:30px}}
</style></head>
<body>
<header>
  <div class="eyebrow">CSI SMART SHIPMENT DATA TRANSFORMATION — ANALYTICS</div>
  <h1>Job #{job_id} — {filename}</h1>
  <p>Engine: {engine} &nbsp;·&nbsp; Mode: {llm_mode} &nbsp;·&nbsp; Generated {generated_at}</p>
</header>
<main>
  <div class="cards">
    <div class="card"><div class="label">Input rows</div><div class="value">{input_rows}</div></div>
    <div class="card"><div class="label">Output rows</div><div class="value">{output_rows}</div><div class="sub">{net_pct}% of input retained</div></div>
    <div class="card"><div class="label">Issues logged</div><div class="value">{total_issues}</div></div>
    <div class="card"><div class="label">AI confidence</div><div class="value">{confidence_pct}%</div><div class="sub"><span class="badge {conf_class}">{conf_label}</span></div></div>
  </div>
  <div class="grid2">
    <div class="panel">
      <h3>Issue breakdown</h3>
      <canvas id="issueChart" height="220"></canvas>
    </div>
    <div class="panel">
      <h3>Row reconciliation</h3>
      <canvas id="reconChart" height="220"></canvas>
    </div>
  </div>
  <div class="panel" style="margin-bottom:20px">
    <h3>Reconciliation detail</h3>
    <table>
      <tr><th>Metric</th><th>Value</th></tr>
      {recon_rows}
    </table>
  </div>
  <div class="panel">
    <h3>Assumptions &amp; review flags</h3>
    <table>
      <tr><th>Assumptions</th><th>Flagged for review</th></tr>
      <tr><td>{assumptions_html}</td><td>{review_html}</td></tr>
    </table>
  </div>
</main>
<footer>Generated locally — no data leaves this file. Open the companion Power BI workbook for full self-service analytics.</footer>
<script>
new Chart(document.getElementById('issueChart'), {{
  type: 'doughnut',
  data: {{ labels: {issue_labels}, datasets: [{{ data: {issue_values}, backgroundColor: ['#5b6cff','#ef476f','#f5a524','#17b978','#8b5cf6','#06b6d4'] }}] }},
  options: {{ plugins: {{ legend: {{ position: 'bottom' }} }} }}
}});
new Chart(document.getElementById('reconChart'), {{
  type: 'bar',
  data: {{ labels: ['Input rows','Output rows','Removed','Flagged'], datasets: [{{ label:'Rows', data: [{input_rows},{output_rows},{removed},{flagged}], backgroundColor:'#5b6cff', borderRadius:6 }}] }},
  options: {{ plugins: {{ legend: {{ display:false }} }}, scales: {{ y: {{ beginAtZero:true }} }} }}
}});
</script>
</body></html>"""


def write_dashboard_html(report, recon, plan, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    breakdown = recon.get("issue_breakdown", {})
    issue_labels = json.dumps(list(breakdown.keys()) or ["No issues"])
    issue_values = json.dumps(list(breakdown.values()) or [1])
    confidence = float(report.get("confidence") or 0)
    conf_class = "good" if confidence >= 0.7 else "warn"
    conf_label = "High confidence" if confidence >= 0.7 else "Review recommended"
    recon_rows = "".join(
        f"<tr><td>{k.replace('_', ' ').title()}</td><td>{v}</td></tr>"
        for k, v in recon.items() if k != "issue_breakdown"
    )
    assumptions_html = "<br>".join(plan.get("assumptions") or ["None"])
    review_html = "<br>".join(plan.get("review") or ["None"])
    html = DASHBOARD_TEMPLATE.format(
        job_id=report["job_id"],
        filename=report["filename"],
        engine=report["engine"],
        llm_mode=report.get("llm_mode", "CSI_LLM"),
        generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        input_rows=recon["input_rows"],
        output_rows=recon["output_rows"],
        net_pct=recon["net_reconciliation_pct"],
        total_issues=recon["total_issues_logged"],
        confidence_pct=round(confidence * 100),
        conf_class=conf_class,
        conf_label=conf_label,
        recon_rows=recon_rows,
        assumptions_html=assumptions_html,
        review_html=review_html,
        issue_labels=issue_labels,
        issue_values=issue_values,
        removed=recon["total_rows_removed_or_flagged"] - recon["rows_flagged_invalid_period"],
        flagged=recon["rows_flagged_invalid_period"],
    )
    path.write_text(html, encoding="utf-8")


def generate_all(job, report, plan, all_output, all_issues, input_rows, null_count, data_dir: Path):
    """Called once per completed job. Returns dict of artifact paths."""
    job_id = job["id"]
    recon = build_reconciliation(job, all_output, all_issues, input_rows, null_count)
    recon_csv = data_dir / "reports" / f"job_{job_id}_reconciliation.csv"
    method_md = data_dir / "reports" / f"job_{job_id}_method_note.md"
    powerbi_xlsx = data_dir / "reports" / f"job_{job_id}_powerbi.xlsx"
    dashboard_html = data_dir / "reports" / f"job_{job_id}_dashboard.html"

    write_reconciliation_csv(recon, recon_csv)
    write_method_note(report, recon, plan, method_md)
    write_powerbi_workbook(all_output, all_issues, recon, report, powerbi_xlsx)
    write_dashboard_html(report, recon, plan, dashboard_html)

    return {
        "reconciliation": str(recon_csv),
        "method_note": str(method_md),
        "powerbi": str(powerbi_xlsx),
        "dashboard": str(dashboard_html),
        "recon": recon,
    }
