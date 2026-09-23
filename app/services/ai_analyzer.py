"""
Local heuristic analysis engine ("Smart Analyzer").

This is the piece that makes the pipeline work end-to-end even when the
NIQ-internal CSI LLM endpoint is unreachable (no VPN, no key, offline demo,
firewall) — which is the most common reason a "cleaning" job previously
failed outright. It produces the exact same transformation-plan shape the
CSI LLM returns (dataset_mode, mapping, period_strategy, matrix_strategy,
transformations, confidence, review, assumptions), using:

  - fuzzy header matching (difflib) against target columns + a synonym bank
    covering the vocabulary seen across the sample files (Pais/Country,
    Marca/Brand, Categoria/Category, Canal/Channel, etc.)
  - statistical column profiling (dtype guesses, cardinality, sample values)
    to disambiguate look-alike columns (e.g. two "channel-ish" columns)
  - period-column detection (wide period headers) and long-period detection
    (Year + Period/Month columns)
  - matrix-layout detection (multi-row dimension headers + Result/Total rows)

The CSI LLM, when reachable, is still preferred (it reasons over more
context and business vocabulary); this module is the guaranteed-available
co-pilot and reviewer underneath it.
"""
import re
from difflib import SequenceMatcher
from collections import Counter

TARGET_COLUMNS = ["Country", "Region", "Channel", "City/State", "Category", "Brand", "SKU", "Fact"]

SYNONYMS = {
    "Country": ["country", "pais", "país", "nation", "market"],
    "Region": ["region", "región", "zone", "zona", "division", "división",
               "subdivision", "subdivisión", "area", "área", "branch", "state region"],
    "Channel": ["channel", "canal", "trade channel", "channel group",
                "channel macro group", "customer grp", "sub channel",
                "trade name", "tradename", "customer"],
    "City/State": ["city", "state", "ciudad", "estado", "city/state", "rsm",
                   "sub trade channel", "location", "province"],
    "Category": ["category", "categoria", "categoría", "global category",
                 "category group", "sub category", "beverage sub category",
                 "segmento", "segment", "mg1_desc", "smalc"],
    "Brand": ["brand", "marca", "brand_desc", "bottler", "marca_desc"],
    "SKU": ["sku", "product", "producto", "product_desc", "product_code",
            "barcode", "description", "format flavor description",
            "mother_pack", "formato", "container", "primary container"],
    "Fact": ["fact", "measure", "metric", "quantity", "value", "sales",
             "volume", "total", "unit", "eaches", "tons"],
}

MONTHS_FULL = ["january", "february", "march", "april", "may", "june", "july",
               "august", "september", "october", "november", "december"]
MONTHS_ABBR = [m[:3] for m in MONTHS_FULL]

PERIOD_HEADER_PATTERNS = [
    re.compile(r"^c\d{4}\s+[A-Za-z]{3,}$", re.I),          # c2025 Feb
    re.compile(r"^\d{2}\.\d{4}$"),                          # 01.2020
    re.compile(r"^(?:%s)[ /_-]\d{4}$" % "|".join(MONTHS_FULL + MONTHS_ABBR), re.I),
    re.compile(r"^\d{4}[-/]\d{1,2}$"),                       # 2024-01
    re.compile(r"^P\d{1,2}$", re.I),                         # P01
]


def _norm(s):
    return re.sub(r"[^a-z0-9]+", " ", str(s).lower()).strip()


def _similarity(a, b):
    return SequenceMatcher(None, a, b).ratio()


def score_column_for_target(col_name, target, sample_values=None):
    """0..1 confidence that `col_name` maps to `target`."""
    n = _norm(col_name)
    best = 0.0
    for syn in [target.lower()] + SYNONYMS.get(target, []):
        best = max(best, _similarity(n, _norm(syn)))
        if _norm(syn) in n or n in _norm(syn):
            best = max(best, 0.82)
    # light value-based tie-breaker: Fact columns tend to be numeric
    if target == "Fact" and sample_values:
        numeric = sum(1 for v in sample_values if _is_numeric(v))
        if numeric / max(1, len(sample_values)) > 0.6:
            best = max(best, 0.55)
    return best


def _is_numeric(v):
    if v is None:
        return False
    if isinstance(v, (int, float)):
        return True
    s = str(v).replace(",", "").replace("$", "").strip()
    try:
        float(s)
        return True
    except ValueError:
        return False


def is_period_header(col_name):
    s = str(col_name).strip()
    return any(p.match(s) for p in PERIOD_HEADER_PATTERNS)


def looks_like_year_column(name, values):
    n = _norm(name)
    if any(k in n for k in ("year", "año", "ano", "displayyear")):
        return True
    nums = [v for v in values if _is_numeric(v)]
    if nums and all(1990 <= float(v) <= 2100 for v in nums[:10]):
        return True
    return False


def looks_like_period_column(name, values):
    n = _norm(name)
    if any(k in n for k in ("period", "periodo", "month", "mes")):
        return True
    for v in values[:10]:
        s = str(v).strip()
        if re.fullmatch(r"P?\d{1,2}", s, re.I):
            return True
    return False


def build_mapping(columns, sample_rows, required_columns):
    """Greedy best-fit assignment: for each target column pick the best unused source column
    above a confidence floor. Below-floor targets are left unmapped (null) and flagged for review."""
    samples_by_col = {c: [r.get(c) for r in sample_rows if isinstance(r, dict)] for c in columns}
    candidates = []
    for target in required_columns:
        if target not in TARGET_COLUMNS:
            continue
        for col in columns:
            s = score_column_for_target(col, target, samples_by_col.get(col))
            candidates.append((s, target, col))
    candidates.sort(key=lambda x: -x[0])

    mapping = {}
    used_cols = set()
    used_targets = set()
    review = []
    for score, target, col in candidates:
        if target in used_targets or col in used_cols:
            continue
        if score < 0.55:
            continue
        mapping[target] = col
        used_cols.add(col)
        used_targets.add(target)
        if score < 0.7:
            review.append(f"Low-confidence mapping: '{col}' -> {target} (score {score:.2f}); please confirm.")

    for target in required_columns:
        if target in TARGET_COLUMNS:
            mapping.setdefault(target, None)
            if mapping[target] is None:
                review.append(f"No confident source column found for target '{target}'.")
    return mapping, review


def detect_period_strategy(columns, sample_rows):
    year_col = period_col = None
    for c in columns:
        vals = [r.get(c) for r in sample_rows if isinstance(r, dict)]
        if year_col is None and looks_like_year_column(c, vals):
            year_col = c
        elif period_col is None and looks_like_period_column(c, vals):
            period_col = c
    if year_col and period_col:
        return {"type": "parse_existing_period_columns", "year_column": year_col, "period_column": period_col}
    return {"type": "keep_columns", "year_column": None, "period_column": None}


def detect_dataset_mode(columns, sample_rows, sheet_snapshot=None):
    period_cols = [c for c in columns if is_period_header(c)]
    period_strategy = detect_period_strategy(columns, sample_rows)
    if period_strategy["year_column"] and period_strategy["period_column"]:
        return "long_period", period_strategy
    if len(period_cols) >= 2:
        return "wide_period", period_strategy
    if sheet_snapshot and _looks_matrix(sheet_snapshot):
        return "matrix", period_strategy
    return "normal", period_strategy


def _looks_matrix(rows, max_scan=8):
    """Multi-row headers stacked above a data grid, commonly with 'Result'/'Total' rows."""
    if not rows or len(rows) < 5:
        return False
    result_hits = 0
    for row in rows[:max_scan]:
        if row and len(row) > 1 and str(row[1]).strip().lower() in ("result", "total", "subtotal"):
            result_hits += 1
    header_like_rows = 0
    for row in rows[:4]:
        non_null = [v for v in row if v not in (None, "")]
        if non_null and all(isinstance(v, str) for v in non_null):
            header_like_rows += 1
    return result_hits >= 1 or header_like_rows >= 3


def analyze(snapshot, required_columns):
    """
    Build a full transformation plan (same schema as the CSI LLM) purely
    from local heuristics. Always succeeds — this is what keeps a job from
    ever hard-failing just because the LLM endpoint is unreachable.
    """
    sheets = snapshot.get("sheets", [])
    usable = [s for s in sheets if s["name"].strip().lower() != "guide"] or sheets
    primary = usable[0] if usable else {"name": "data", "columns": [], "rows": []}
    columns = primary.get("columns") or (primary.get("rows", [[]])[0] if primary.get("rows") else [])
    rows = primary.get("rows", [])
    header_row_ix = primary.get("likely_header_row", 1)
    sample_rows = []
    for r in rows[header_row_ix:header_row_ix + 12]:
        sample_rows.append(dict(zip(columns, r)))

    dataset_mode, period_strategy = detect_dataset_mode(columns, sample_rows, rows)
    mapping, review = build_mapping(columns, sample_rows, required_columns)

    matrix_strategy = {"enabled": dataset_mode == "matrix", "dimension_rows": [1, 2, 3],
                        "value_start_row": 5, "unit_row": 4, "skip_if_result_in": "B"}

    transformations = []
    if any(is_period_header(c) for c in columns):
        transformations.append({"rule": "normalize_period_headers", "columns": [c for c in columns if is_period_header(c)],
                                 "reason": "Wide period headers detected; normalized to YYYY-MM."})
    if period_strategy["year_column"]:
        transformations.append({"rule": "pivot_long_period_to_columns", "columns": [period_strategy["year_column"], period_strategy["period_column"]],
                                 "reason": "Year + Period columns detected; pivoted into one column per period and aggregated the fact column."})
    transformations.append({"rule": "trim_and_deduplicate", "columns": ["*"],
                             "reason": "Applied to every column: trim whitespace, drop blank rows, drop exact duplicates."})

    mapped = sum(1 for v in mapping.values() if v)
    confidence = round(0.35 + 0.55 * (mapped / max(1, len([c for c in required_columns if c in TARGET_COLUMNS]))), 2)
    if dataset_mode == "matrix":
        confidence = min(confidence, 0.6)

    assumptions = [
        "Generated locally by the Smart Analyzer heuristic engine (CSI LLM endpoint unavailable or disabled) — "
        "mapping is fuzzy-matched from header text and column value shapes.",
    ]
    if dataset_mode == "long_period":
        assumptions.append(f"Treated '{period_strategy['year_column']}' + '{period_strategy['period_column']}' as the "
                            "year/period pair and pivoted the fact column into one column per period.")
    if dataset_mode == "matrix":
        assumptions.append("Detected a matrix layout (stacked dimension header rows + Result/Total rows); "
                            "Result/Total rows are excluded from atomic output per guardrails.")

    return {
        "dataset_mode": dataset_mode,
        "sheet_plans": [{"sheet": s["name"], "header_row": s.get("likely_header_row", 1)} for s in usable],
        "mapping": mapping,
        "transformations": transformations,
        "period_strategy": period_strategy,
        "matrix_strategy": matrix_strategy,
        "confidence": confidence,
        "review": review,
        "assumptions": assumptions,
        "mode": "SMART_ANALYZER",
    }
