from pathlib import Path
from uuid import uuid4
from app.config import DATA

ALLOWED={".csv",".xlsx",".xls",".txt",".tsv",".json",".xml",".parquet"}

def safe_filename(name):
    p=Path(name or "upload")
    ext=p.suffix.lower()
    if ext not in ALLOWED: raise ValueError(f"Unsupported file type: {ext or 'unknown'}")
    stem="".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in p.stem)[:100]
    return f"{stem}_{uuid4().hex[:10]}{ext}"

def path_for(folder,name): return DATA/folder/name
