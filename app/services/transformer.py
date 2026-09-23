import re, json, csv, shutil
from pathlib import Path
from datetime import datetime
import polars as pl
from app.schemas import TARGET_COLUMNS

PERIOD_PATTERNS=[re.compile(r"^c\d{4}\s+[A-Za-z]+$",re.I),re.compile(r"^\d{2}\.\d{4}$"),re.compile(r"^(?:January|February|March|April|May|June|July|August|September|October|November|December)[ /-]\d{4}$",re.I),re.compile(r"^\d{4}[-/]\d{1,2}$")]

def is_period_column(c): return any(p.match(str(c).strip()) for p in PERIOD_PATTERNS)
def normalize_period(c):
    s=str(c).strip()
    m=re.match(r"^c(\d{4})\s+([A-Za-z]+)$",s,re.I)
    if m:
        for fmt in ["%b %Y","%B %Y"]:
            try:return datetime.strptime(f"{m.group(2)} {m.group(1)}",fmt).strftime("%Y-%m")
            except:pass
    m=re.match(r"^(\d{2})\.(\d{4})$",s)
    if m:return f"{m.group(2)}-{m.group(1)}"
    m=re.match(r"^([A-Za-z]+)[ /-](\d{4})$",s)
    if m:
        try:return datetime.strptime(f"{m.group(1)} {m.group(2)}","%B %Y").strftime("%Y-%m")
        except:pass
    m=re.match(r"^(\d{4})[-/](\d{1,2})$",s)
    if m:return f"{m.group(1)}-{int(m.group(2)):02d}"
    return s

def parse_long_period(row,year_col,period_col):
    y=row.get(year_col); p=row.get(period_col)
    if y is None or p is None:return None
    m=re.search(r"(?:P)?(\d{1,2})",str(p),re.I)
    if not m:return None
    mo=int(m.group(1))
    return f"{int(float(y)):04d}-{mo:02d}" if 1<=mo<=12 else None

def base_target_row(src,mapping,selected,source_row):
    row={}
    trace={}
    for target in selected:
        sc=mapping.get(target)
        row[target]=src.get(sc) if sc else None
        trace[target]=sc
    row["_source_row"]=source_row; row["_source_trace"]=json.dumps(trace)
    return row

def transform_records(records,plan,required_columns):
    mapping=plan.get("mapping",{})
    selected=[c for c in required_columns if c in TARGET_COLUMNS]
    issues=[]; out=[]
    mode=plan.get("dataset_mode","unknown")
    period=plan.get("period_strategy",{}) or {}
    if mode=="long_period" or (period.get("year_column") and period.get("period_column")):
        ycol,pcol=period.get("year_column"),period.get("period_column")
        fact=mapping.get("Fact")
        grouped={}
        for i,src in enumerate(records,1):
            per=parse_long_period(src,ycol,pcol)
            if not per:
                issues.append({"source_row":i,"issue_type":"INVALID_PERIOD","detail":"Could not parse year/period"}); continue
            key=tuple(src.get(mapping.get(t)) if mapping.get(t) else None for t in selected if t!="Fact")
            if key not in grouped:
                grouped[key]=base_target_row(src,mapping,selected,i)
            grouped[key][per]=(grouped[key].get(per) or 0)+(src.get(fact) or 0)
        out=list(grouped.values())
        return out,issues
    if mode=="matrix" or (plan.get("matrix_strategy",{}) or {}).get("enabled"):
        return out,issues
    for i,src in enumerate(records,1):
        vals=" ".join(str(v) for v in src.values() if v is not None)
        if re.search(r"\b(Result|Subtotal|Total)\b",vals,re.I):
            issues.append({"source_row":i,"issue_type":"AGGREGATE_ROW","detail":"Subtotal/Result/Total row excluded"}); continue
        row=base_target_row(src,mapping,selected,i)
        for c,v in src.items():
            if is_period_column(c): row[normalize_period(c)]=v
        out.append(row)
    return out,issues

def transform_matrix(sheet_rows,plan,required_columns,unit):
    # Generic matrix convention used by the challenge: first rows carry dimension labels,
    # the unit row identifies the measure, and subsequent rows contain month/value cells.
    issues=[]; out=[]
    if len(sheet_rows)<5:return out,issues
    unit_row=(plan.get("matrix_strategy",{}) or {}).get("unit_row") or 4
    data_start=(plan.get("matrix_strategy",{}) or {}).get("value_start_row") or 5
    # 1-indexed in the AI plan; convert to Python indices.
    ur=max(1,unit_row)-1; ds=max(1,data_start)-1
    header=sheet_rows[ur]
    for rix,row in enumerate(sheet_rows[ds:],start=ds+1):
        if len(row)>1 and str(row[1]).strip().lower()=="result":
            issues.append({"source_row":rix,"issue_type":"AGGREGATE_ROW","detail":"Result row excluded from atomic output"}); continue
        dateval=row[0] if row else None
        period=normalize_period(dateval) if dateval is not None else None
        if not period: continue
        # In matrix sheets, columns B-E are product dimensions and F+ are channel values.
        for col_idx in range(5,len(row)):
            val=row[col_idx]
            if val in (None,""): continue
            ch=str(sheet_rows[0][col_idx]).strip() if col_idx<len(sheet_rows[0]) else None
            grp=str(sheet_rows[1][col_idx]).strip() if col_idx<len(sheet_rows[1]) else None
            sub=str(sheet_rows[2][col_idx]).strip() if col_idx<len(sheet_rows[2]) else None
            category=row[1] if len(row)>1 else None
            brand=row[2] if len(row)>2 else None
            segment=row[3] if len(row)>3 else None
            fmt=row[4] if len(row)>4 else None
            base={"Country":None,"Region":None,"Channel":ch,"City/State":None,"Category":category,"Brand":brand,"SKU":fmt or segment,"Fact":unit,"_source_row":rix,"_source_trace":json.dumps({"Category":"B","Brand":"C","SKU":"E","Channel":f"{chr(65+col_idx)} header rows 1-3","Fact":f"{unit} sheet"})}
            base[period]=val
            out.append({k:v for k,v in base.items() if k in set(required_columns)|{period,"_source_row","_source_trace"}})
    return out,issues

def write_output(rows,path):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    if not rows:
        pl.DataFrame({c:[] for c in TARGET_COLUMNS}).write_csv(path); return
    df=pl.from_dicts(rows,strict=False)
    df=df.select([c for c in df.columns if not c.startswith("_")])
    if path.suffix.lower()==".xlsx": df.write_excel(path,worksheet="Cleaned Data",autofit=True)
    elif path.suffix.lower()==".parquet": df.write_parquet(path)
    else: df.write_csv(path)
