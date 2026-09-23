import sqlite3
from pathlib import Path
from contextlib import contextmanager
from datetime import datetime, timezone
from app.config import DATA

DB_PATH = DATA / "smart_transformer.db"

@contextmanager
def conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    try:
        yield c
        c.commit()
    finally:
        c.close()

def init_db():
    with conn() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS users (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          username TEXT UNIQUE NOT NULL,
          password_hash TEXT NOT NULL,
          created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS jobs (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          filename TEXT NOT NULL,
          stored_path TEXT NOT NULL,
          size_bytes INTEGER NOT NULL,
          engine TEXT,
          status TEXT NOT NULL,
          progress INTEGER NOT NULL DEFAULT 0,
          stage TEXT,
          row_count INTEGER,
          output_rows INTEGER,
          null_count INTEGER,
          issue_count INTEGER,
          llm_mode TEXT,
          confidence REAL,
          output_path TEXT,
          error_path TEXT,
          report_path TEXT,
          reconciliation_path TEXT,
          method_note_path TEXT,
          powerbi_path TEXT,
          dashboard_path TEXT,
          error_message TEXT,
          created_at TEXT NOT NULL,
          started_at TEXT,
          completed_at TEXT
        );
        CREATE TABLE IF NOT EXISTS templates (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          name TEXT UNIQUE NOT NULL,
          description TEXT,
          columns_json TEXT NOT NULL,
          rules_json TEXT NOT NULL,
          created_at TEXT NOT NULL
        );
        ''')
        existing = {r[1] for r in c.execute("PRAGMA table_info(jobs)").fetchall()}
        for col in ("reconciliation_path", "method_note_path", "powerbi_path", "dashboard_path"):
            if col not in existing:
                c.execute(f"ALTER TABLE jobs ADD COLUMN {col} TEXT")

def now(): return datetime.now(timezone.utc).isoformat()

def create_job(filename, stored_path, size_bytes):
    with conn() as c:
        cur=c.execute("INSERT INTO jobs(filename,stored_path,size_bytes,status,created_at) VALUES(?,?,?,?,?)",
                      (filename,stored_path,size_bytes,"QUEUED",now()))
        return cur.lastrowid

def update_job(job_id, **fields):
    if not fields: return
    allowed={"engine","status","progress","stage","row_count","output_rows","null_count","issue_count","llm_mode","confidence","output_path","error_path","report_path","reconciliation_path","method_note_path","powerbi_path","dashboard_path","error_message","started_at","completed_at"}
    fields={k:v for k,v in fields.items() if k in allowed}
    with conn() as c:
        sql="UPDATE jobs SET "+", ".join(f"{k}=?" for k in fields)+" WHERE id=?"
        c.execute(sql, [*fields.values(),job_id])

def get_job(job_id):
    with conn() as c:
        r=c.execute("SELECT * FROM jobs WHERE id=?",(job_id,)).fetchone()
        return dict(r) if r else None

def list_jobs(limit=100):
    with conn() as c:
        return [dict(r) for r in c.execute("SELECT * FROM jobs ORDER BY id DESC LIMIT ?",(limit,)).fetchall()]

def upsert_user(username, password_hash):
    with conn() as c:
        c.execute("INSERT INTO users(username,password_hash,created_at) VALUES(?,?,?) ON CONFLICT(username) DO UPDATE SET password_hash=excluded.password_hash",(username,password_hash,now()))

def get_user(username):
    with conn() as c:
        r=c.execute("SELECT * FROM users WHERE username=?",(username,)).fetchone()
        return dict(r) if r else None

def list_templates():
    with conn() as c:
        return [dict(r) for r in c.execute("SELECT * FROM templates ORDER BY name").fetchall()]

def save_template(name, description, columns, rules):
    import json
    with conn() as c:
        c.execute("INSERT INTO templates(name,description,columns_json,rules_json,created_at) VALUES(?,?,?,?,?) ON CONFLICT(name) DO UPDATE SET description=excluded.description,columns_json=excluded.columns_json,rules_json=excluded.rules_json",
                  (name,description,json.dumps(columns),json.dumps(rules),now()))
