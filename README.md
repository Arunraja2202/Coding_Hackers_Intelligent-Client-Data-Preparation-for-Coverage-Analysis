# CSI Smart Shipment Data Transformation Platform

Enterprise-style FastAPI application for ingesting client shipment files, profiling structure, calling the approved CSI LLM for a transformation plan, applying deterministic cleaning/mapping, and producing a target dataset, issue log and reconciliation report.

## CSI LLM integration

The CSI integration follows the supplied `test(5).ipynb` reference:

- Endpoint: `https://llm-api-cis.azure-intlsd-np.nielsencsp.net/`
- SDK: `azure.ai.inference.ChatCompletionsClient`
- Credential: `AzureKeyCredential`
- API version: `2025-03-01-preview`
- Model: `hack-fest-gpt-5.6-luna`
- `Authorization` header uses the configured API key value.

Put the approved key in `.env` as `CSI_LLM_API_KEY=Bearer <YOUR_API_KEY>`.

## Engine selection

The file size is checked before processing:

- `<= 1 GiB`: Polars
- `> 1 GiB`: PySpark

For Excel, the workbook reader streams selected sheets to a temporary CSV before Polars processing. This avoids loading a full workbook into pandas. Matrix-style multi-tab workbooks are parsed as a structured matrix and then materialized through the output pipeline.

## Run locally

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python scripts/create_admin.py
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000`.

Default credentials are controlled by `.env` (`admin` / `ChangeMe123!` in the example).

For >1 GiB jobs install PySpark:

```powershell
pip install -r requirements-large.txt
```

## Docker

```powershell
copy .env.example .env
docker compose up --build
```

## AI analysis — CSI LLM with an offline fallback

The transformation plan (header/column mapping, period strategy, matrix detection, confidence, review flags) is produced by:

1. **CSI LLM** (`app/services/llm.py`) — the approved NIQ-internal endpoint, used whenever it's reachable and configured.
2. **Smart Analyzer** (`app/services/ai_analyzer.py`) — a local, dependency-free heuristic engine (fuzzy header matching against a multilingual synonym bank, column-value profiling, period/matrix pattern detection) that runs automatically whenever the CSI LLM is disabled, misconfigured, unreachable, or times out.

This means a job never hard-fails just because the CSI endpoint isn't reachable (e.g. off the corporate network, no key configured yet, offline demo) — it transparently falls back and the report/dashboard always show which engine actually produced the plan (`llm_mode: CSI_LLM` or `SMART_ANALYZER`).

## Outputs per job

Every completed job produces the full set of "must-have" deliverables from the challenge brief, all downloadable from the UI (Home, History or Analytics pages):

- **Cleaned dataset** — target-structure output (`.xlsx`/`.csv`/`.parquet`)
- **Data-quality issue log** — every excluded/flagged row with a reason
- **Reconciliation summary** — input vs output row counts, removals by type
- **Method note** — short write-up of AI use, assumptions, confidence, review flags
- **Power BI-ready workbook** — `Cleaned_Data` / `Issue_Log` / `Reconciliation_Summary` / `Run_Info` sheets, ready for `Get Data → Excel` in Power BI Desktop (see `docs/POWERBI_GUIDE.md`)
- **Interactive dashboard** — a self-contained HTML file (Chart.js) you can open standalone or view in-app at `/api/jobs/{id}/dashboard`

There's also an **Analytics** page (`/analytics`) giving a portfolio-level view (jobs by status, engine mix, KPIs) across the whole job history.

## Output / guardrails

The target fields are `Country, Region, Channel, City/State, Category, Brand, SKU, Fact`; source time periods remain columns. The job report records mapping, assumptions, confidence, issue count, duration and guardrails. Blank rows and exact duplicates are removed, text is trimmed, dates/emails/phones are normalized where recognizable, and `Result`/`Total` aggregate rows are excluded from atomic output. No source value is invented by the deterministic layer.

## Project layout

- `app/api`: REST endpoints
- `app/services`: ingestion, profiling, CSI client, cleaning, transformation, job orchestration, storage
- `app/templates`: Bootstrap UI
- `app/static`: CSS/JS
- `data`: local runtime storage; no sample datasets are bundled
- `tests`: automated checks
