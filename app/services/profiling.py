import json, math
from pathlib import Path
import polars as pl

PERIOD_HINTS=("c2025 ","c2024 ","calendar year/month","period","periodo")

def choose_engine(path: Path, max_bytes: int):
    return "POLARS" if path.stat().st_size <= max_bytes else "PYSPARK"

def profile_polars(df: pl.DataFrame):
    nulls=sum(df[c].null_count() for c in df.columns)
    types=[{"name":c,"dtype":str(df[c].dtype),"null_count":df[c].null_count()} for c in df.columns]
    sample=df.head(8).to_dicts()
    return {"columns":types,"row_count":df.height,"null_count":nulls,"sample_rows":sample}

def sample_file_metadata(path: Path, max_rows=12):
    ext=path.suffix.lower()
    if ext == ".xlsx":
        from .workbook import workbook_snapshot
        return workbook_snapshot(path,max_rows)
    if ext == ".xls":
        from .workbook import read_xls_snapshot
        return read_xls_snapshot(path,max_rows)
    if ext in {".csv",".tsv",".txt"}:
        sep="\t" if ext==".tsv" else ","
        try: df=pl.read_csv(path, separator=sep, n_rows=max_rows, infer_schema_length=100)
        except Exception: df=pl.read_csv(path, separator=sep, n_rows=max_rows, has_header=False)
        return {"sheets":[{"name":"data","columns":df.columns,"sample_rows":df.to_dicts()}]}
    if ext==".parquet":
        df=pl.read_parquet(path,n_rows=max_rows)
        return {"sheets":[{"name":"data","columns":df.columns,"sample_rows":df.to_dicts()}]}
    if ext==".json":
        raw=json.loads(path.read_text(encoding="utf-8"))
        rows=raw if isinstance(raw,list) else raw.get("data",raw.get("rows",[raw])) if isinstance(raw,dict) else []
        rows=rows[:max_rows]
        cols=list(rows[0].keys()) if rows and isinstance(rows[0],dict) else []
        return {"sheets":[{"name":"data","columns":cols,"sample_rows":rows}]}
    if ext==".xml":
        import xml.etree.ElementTree as ET
        root=ET.parse(path).getroot(); rows=[]
        for elem in list(root)[:max_rows]:
            rows.append({child.tag.split("}")[-1]:child.text for child in list(elem)})
        cols=list(rows[0].keys()) if rows else []
        return {"sheets":[{"name":"data","columns":cols,"sample_rows":rows}]}
    raise ValueError("Unsupported file type")
