# Power BI dashboard guide

Every completed job produces a ready-to-use analytics package:

| Artifact | Where | Use |
|---|---|---|
| `job_{id}_dashboard.html` | Download button "View dashboard" / `/api/jobs/{id}/dashboard` | Instant, self-contained interactive dashboard (Chart.js). Opens in any browser, no install, downloadable and shareable as one file. |
| `job_{id}_powerbi.xlsx` | Download button "Power BI workbook" | Multi-sheet workbook (`Cleaned_Data`, `Issue_Log`, `Reconciliation_Summary`, `Run_Info`) formatted for Power BI ingestion. |
| `job_{id}_reconciliation.csv` | Download button "Reconciliation" | Flat reconciliation summary (input vs output rows, removals, issue counts). |
| `job_{id}_method_note.md` | Download button "Method note" | Short note on AI use, assumptions, confidence and review flags — a must-have deliverable per the challenge brief. |

## Building a live Power BI Desktop report from the workbook

1. Open **Power BI Desktop** → **Get Data** → **Excel workbook** → select `job_{id}_powerbi.xlsx`.
2. In the Navigator, check **Cleaned_Data**, **Issue_Log**, **Reconciliation_Summary**, and **Run_Info**, then **Load**.
3. In **Model view**, no relationships are required for a single-job report; for a multi-job portfolio report, load several `*_powerbi.xlsx` files with **Get Data → Folder** and append them (Power Query → `Combine & Transform`), then relate `Run_Info[job_id]` to `Cleaned_Data[job_id]` if you add a `job_id` column during append.
4. Suggested visuals:
   - **Card**: `Run_Info[confidence]`, `Run_Info[input_rows]`, `Run_Info[output_rows]`.
   - **Donut chart**: `Issue_Log[issue_type]` count.
   - **Table**: `Reconciliation_Summary`.
   - **Clustered bar**: `Cleaned_Data` rows by `Category`/`Brand`/`Channel` (whichever target columns are populated), with the trailing month columns as a matrix/heatmap.
5. Publish to the Power BI Service if you want a hosted, shareable report; the in-app HTML dashboard already gives a zero-install option for a live demo.

## Why not a pre-built `.pbix`?

A `.pbix` file is a binary produced by Power BI Desktop itself; it can't be authored outside that application. Shipping a ready-made, cleanly structured Excel workbook (above) is the standard way to hand off a Power BI-ready data source — opening it and clicking **Load** reproduces the exact same report in under a minute, and it stays reproducible for every new job without regenerating a `.pbix` by hand.
