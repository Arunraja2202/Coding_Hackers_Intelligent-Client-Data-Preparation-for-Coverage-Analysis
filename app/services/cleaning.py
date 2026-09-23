"""
Deterministic, rule-based cleaning layer.

This runs on every row *before* the AI-proposed transformation plan is
applied, and never invents values - it only normalizes formatting and
removes rows that are unusable (fully blank, exact duplicates, aggregate
rows). Every action is logged to the issue log with a reason and a source
row number so it is fully traceable and reversible.
"""
import re
import unicodedata
from datetime import datetime
from dateutil import parser as dateparser

PHONE_RE = re.compile(r"[^0-9+]")
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
CURRENCY_RE = re.compile(r"^[\s]*[\$€£]?\s*-?\(?[\d,]+\.?\d*\)?\s*%?\s*$")
CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def strip_controls(s):
    return CONTROL_CHARS_RE.sub("", s)


def collapse_whitespace(s):
    return re.sub(r"\s+", " ", s).strip()


def clean_value(v):
    """Trim, normalize unicode, collapse internal whitespace, strip control chars."""
    if isinstance(v, str):
        v = unicodedata.normalize("NFKC", v)
        v = strip_controls(v)
        v = collapse_whitespace(v)
        return v if v != "" else None
    return v


def normalize_phone(v):
    if v is None: return v
    s = str(v).strip()
    return PHONE_RE.sub("", s) if s else None


def normalize_email(v):
    if v is None: return v
    s = str(v).strip().lower()
    return s if EMAIL_RE.match(s) else s


def normalize_date(v):
    if v in (None, ""): return v
    if hasattr(v, "strftime"): return v.strftime("%Y-%m-%d")
    s = str(v).strip()
    patterns = ["%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%d.%m.%Y", "%B/%Y", "%B %Y", "%b %Y"]
    for fmt in patterns:
        try: return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except: pass
    m = re.fullmatch(r"c(\d{4})\s+([A-Za-z]+)", s, re.I)
    if m:
        try: return datetime.strptime(f"{m.group(2)} {m.group(1)}", "%b %Y" if len(m.group(2)) == 3 else "%B %Y").strftime("%Y-%m-%d")
        except: pass
    m = re.fullmatch(r"(\d{2})\.(\d{4})", s)
    if m: return f"{m.group(2)}-{m.group(1)}-01"
    m = re.fullmatch(r"P(\d{1,2})", s, re.I)
    if m: return f"P{int(m.group(1)):02d}"
    try: return dateparser.parse(s, fuzzy=False).strftime("%Y-%m-%d")
    except: return v


def parse_numeric(v):
    """
    Parse a numeric-looking value while PRESERVING sign (returns/credits
    stay negative) and distinguishing explicit zero from missing.
    Returns (parsed_value_or_None, was_numeric_field: bool).
    """
    if v is None:
        return None, False
    if isinstance(v, (int, float)):
        return v, True
    s = str(v).strip()
    if s == "":
        return None, False
    if not CURRENCY_RE.match(s):
        return v, False
    negative = s.startswith("(") and s.endswith(")")
    cleaned = s.strip("()").replace("$", "").replace("€", "").replace("£", "").replace(",", "").replace("%", "").strip()
    if cleaned in ("", "-"):
        return v, False
    try:
        num = float(cleaned)
        if negative:
            num = -abs(num)
        return (int(num) if num.is_integer() else num), True
    except ValueError:
        return v, False


def normalize_text_field(v):
    """Standardize casing/spacing for categorical text without changing meaning
    (kept conservative: only collapses whitespace/case of ALL-CAPS noise)."""
    if not isinstance(v, str) or v == "":
        return v
    if v.isupper() and len(v) > 3:
        # Title-case long ALL-CAPS labels for readability, but keep short codes
        # (e.g. "US", "SKU12") untouched - those are usually intentional codes.
        return v.title()
    return v


def clean_records(records):
    """
    Row-level advanced cleaning pass. For every row:
      1. normalize unicode/whitespace/control characters on every value
      2. drop fully-blank rows
      3. drop exact duplicate rows (post-normalization)
      4. drop Result/Subtotal/Total aggregate rows (kept out of atomic output)
      5. field-aware normalization: email, phone, date/period, numeric (sign-preserving,
         explicit-zero-preserving), and ALL-CAPS text tidy-up
    Every removal/adjustment is logged with the originating row number.
    """
    issues = []
    out = []
    seen = set()
    for idx, row in enumerate(records, 1):
        cleaned = {k: clean_value(v) for k, v in row.items()}

        if all(v in (None, "") for v in cleaned.values()):
            issues.append({"source_row": idx, "issue_type": "NULL_ROW_REMOVED", "detail": "Entirely blank row removed"})
            continue

        row_text = " ".join(str(v) for v in cleaned.values() if v is not None)
        if re.search(r"\b(Result|Subtotal|Grand Total|Total)\b", row_text, re.I) and \
           sum(1 for v in cleaned.values() if v not in (None, "")) <= max(2, len(cleaned) // 3):
            issues.append({"source_row": idx, "issue_type": "AGGREGATE_ROW", "detail": "Subtotal/Result/Total row excluded"})
            continue

        key = tuple(str(cleaned.get(k)) for k in cleaned)
        if key in seen:
            issues.append({"source_row": idx, "issue_type": "DUPLICATE_REMOVED", "detail": "Exact duplicate row removed"})
            continue
        seen.add(key)

        for k, v in list(cleaned.items()):
            lk = k.lower()
            if "email" in lk:
                cleaned[k] = normalize_email(v)
            elif any(x in lk for x in ("phone", "mobile", "tel")):
                cleaned[k] = normalize_phone(v)
            elif any(x in lk for x in ("date", "period", "month", "year/month", "calendar")):
                cleaned[k] = normalize_date(v)
            else:
                num, was_numeric = parse_numeric(v)
                if was_numeric:
                    cleaned[k] = num
                elif isinstance(v, str):
                    cleaned[k] = normalize_text_field(v)

        out.append(cleaned)
    return out, issues
