# Method Note — Job #1 (example_1_easy.xlsx)

_Generated 2026-09-23T22:37:21+00:00Z_

## AI use
- Engine selected: **POLARS** (Polars for files ≤ 1 GiB, PySpark above).
- Mapping/interpretation produced by the CSI LLM (`CSI_LLM`).
- Reported model confidence: **0.96**.
- The LLM only proposes a transformation *plan* (column mapping, period strategy, matrix handling, confidence, review flags). All data movement — reading, cleaning, aggregation, writing — is executed by deterministic code so no AI output is written to client data directly.

## Assumptions
- Rows in Data beginning at row 2 are detail records.
- L1,2 - Division is used as Region because its description identifies it as the region of the country.
- L1,1 - Subdivision is used as City/State because its description identifies it as a more specific regional subdivision.
- Trade Channel is used as Channel because its column name explicitly describes the channel.
- Global Category is used as Category because its description explicitly defines a global category.
- Each cYYYY Mon column is a numeric Fact column for the month represented by its header.

## Flagged for human review (low-confidence / ambiguous)
- Country has no explicit source column and must remain null.
- SKU has no explicit source column; Brand must not be used as a SKU substitute.
- The Guide sheet is documentation and should not be transformed as shipment data.
- Fact represents the numeric values in the period columns rather than a single source column.

## Transformations applied
- **Retain the identifying columns and preserve the existing period columns as separate output columns.** — columns: L1,2 - Division, Trade Channel, L1,1 - Subdivision, Global Category, Brand, c2025 Feb, c2025 May, c2025 Jun, c2023 Mar, c2025 Jul, c2024 Jul, c2025 Nov, c2023 Jan, c2024 May, c2025 Mar, c2024 Dec, c2024 Jun, c2024 Aug, c2023 Aug, c2023 Jun, c2025 Sep, c2025 Aug, c2024 Apr, c2025 Apr, c2024 Sep, c2023 Dec, c2025 Oct, c2024 Mar, c2023 May, c2026 Jan, c2025 Dec, c2023 Sep, c2023 Oct, c2023 Nov, c2024 Nov, c2024 Jan, c2023 Jul, c2024 Feb, c2023 Feb, c2025 Jan, c2024 Oct, c2023 Apr — The Data sheet is a wide period table with dates encoded in column names.
- **Parse period headers using the cYYYY Mon format and normalize their date interpretation without reordering source period columns unless explicitly requested.** — columns: c2025 Feb, c2025 May, c2025 Jun, c2023 Mar, c2025 Jul, c2024 Jul, c2025 Nov, c2023 Jan, c2024 May, c2025 Mar, c2024 Dec, c2024 Jun, c2024 Aug, c2023 Aug, c2023 Jun, c2025 Sep, c2025 Aug, c2024 Apr, c2025 Apr, c2024 Sep, c2023 Dec, c2025 Oct, c2024 Mar, c2023 May, c2026 Jan, c2025 Dec, c2023 Sep, c2023 Oct, c2023 Nov, c2024 Nov, c2024 Jan, c2023 Jul, c2024 Feb, c2023 Feb, c2025 Jan, c2024 Oct, c2023 Apr — All period headers follow an explicit year-month naming convention, including nonchronological ordering.
- **Preserve explicit numeric zero values as zero and preserve null or missing source cells as null/missing; do not impute values.** — columns: c2025 Feb, c2025 May, c2025 Jun, c2023 Mar, c2025 Jul, c2024 Jul, c2025 Nov, c2023 Jan, c2024 May, c2025 Mar, c2024 Dec, c2024 Jun, c2024 Aug, c2023 Aug, c2023 Jun, c2025 Sep, c2025 Aug, c2024 Apr, c2025 Apr, c2024 Sep, c2023 Dec, c2025 Oct, c2024 Mar, c2023 May, c2026 Jan, c2025 Dec, c2023 Sep, c2023 Oct, c2023 Nov, c2024 Nov, c2024 Jan, c2023 Jul, c2024 Feb, c2023 Feb, c2025 Jan, c2024 Oct, c2023 Apr — The source contains both explicit zeros and nulls, which have different meanings and must remain distinct.
- **Do not exclude or convert negative numeric values if encountered; preserve signed returns in the corresponding period column.** — columns: c2025 Feb, c2025 May, c2025 Jun, c2023 Mar, c2025 Jul, c2024 Jul, c2025 Nov, c2023 Jan, c2024 May, c2025 Mar, c2024 Dec, c2024 Jun, c2024 Aug, c2023 Aug, c2023 Jun, c2025 Sep, c2025 Aug, c2024 Apr, c2025 Apr, c2024 Sep, c2023 Dec, c2025 Oct, c2024 Mar, c2023 May, c2026 Jan, c2025 Dec, c2023 Sep, c2023 Oct, c2023 Nov, c2024 Nov, c2024 Jan, c2023 Jul, c2024 Feb, c2023 Feb, c2025 Jan, c2024 Oct, c2023 Apr — Signed returns must remain traceable and must not be coerced to positive values.

## Reconciliation at a glance
- Input rows profiled: **19**
- Output rows produced: **19** (100.0% of input)
- Rows removed (blank/duplicate/subtotal): **0**
- Issues logged: **0**

## Guardrails honored
- source trace retained
- explicit zero preserved
- signed values preserved
- low-confidence mappings flagged
- Result/Total rows excluded from atomic output