from pathlib import Path
import json, os
from fastapi import APIRouter, UploadFile, File, Form, BackgroundTasks, Request, HTTPException
from fastapi.responses import FileResponse, RedirectResponse, HTMLResponse
from app import db
from app.config import settings, DATA
from app.schemas import LoginRequest, TransformRequest, TARGET_COLUMNS
from app.services.security import verify_password, make_session, read_session
from app.services.storage import safe_filename, path_for
from app.services.jobs import submit
from app.services.workbook import workbook_snapshot

router=APIRouter()

def current_user(request):
    token=request.cookies.get("session")
    user=read_session(token) if token else None
    return user

def require_user(request):
    u=current_user(request)
    if not u: raise HTTPException(401,"Authentication required")
    return u


@router.post("/api/login")
def login(username: str = Form(...), password: str = Form(...)):
    user = db.get_user(username)

    if not user or not verify_password(password, user["password_hash"]):
        raise HTTPException(401, "Invalid username or password")

    response = RedirectResponse("/", status_code=303)

    response.set_cookie(
        "session",
        make_session(username),
        httponly=True,
        samesite="lax",
        max_age=86400
    )

    return response
@router.post("/api/logout")
def logout():
    r=RedirectResponse("/login",status_code=303); r.delete_cookie("session"); return r

@router.get("/api/templates")
def templates(request:Request):
    require_user(request); return db.list_templates()

@router.post("/api/templates")
def save_template(request:Request, name:str=Form(...), description:str=Form(""), columns:str=Form(...), rules:str=Form("{}")):
    require_user(request)
    try: cols=json.loads(columns); rs=json.loads(rules)
    except: raise HTTPException(400,"columns/rules must be JSON")
    db.save_template(name,description,cols,rs); return {"ok":True}

@router.get("/api/jobs")
def jobs(request:Request): require_user(request); return db.list_jobs()

@router.get("/api/jobs/{job_id}")
def job(request:Request,job_id:int):
    require_user(request); j=db.get_job(job_id)
    if not j: raise HTTPException(404,"Job not found")
    return j

@router.post("/api/upload")
async def upload(request:Request, background:BackgroundTasks, file:UploadFile=File(...), required_columns:str=Form("Country,Region,Channel,City/State,Category,Brand,SKU,Fact"), template_name:str=Form("")):
    require_user(request)
    try:
        name=safe_filename(file.filename)
    except ValueError as e:
        raise HTTPException(400,str(e))
    target=path_for("uploads",name)
    max_bytes=int(settings.max_upload_gb*1024**3); written=0
    with target.open("wb") as f:
        while chunk:=await file.read(1024*1024):
            written+=len(chunk)
            if written>max_bytes: target.unlink(missing_ok=True); raise HTTPException(413,"File exceeds configured upload limit")
            f.write(chunk)
    try: cols=[c.strip() for c in required_columns.split(",") if c.strip()]
    except: cols=TARGET_COLUMNS
    job_id=db.create_job(file.filename,str(target),written)
    submit(job_id,cols,template_name or None)
    return {"job_id":job_id,"filename":file.filename,"size_bytes":written,"engine":"POLARS" if written<=settings.polars_max_bytes else "PYSPARK"}

@router.get("/api/jobs/{job_id}/download/{kind}")
def download(request:Request,job_id:int,kind:str):
    require_user(request); j=db.get_job(job_id)
    if not j: raise HTTPException(404,"Job not found")
    p={
        "output":j.get("output_path"),
        "errors":j.get("error_path"),
        "report":j.get("report_path"),
        "reconciliation":j.get("reconciliation_path"),
        "method_note":j.get("method_note_path"),
        "powerbi":j.get("powerbi_path"),
        "dashboard":j.get("dashboard_path"),
    }.get(kind)
    if not p or not Path(p).exists(): raise HTTPException(404,"Artifact not available")
    return FileResponse(p,filename=Path(p).name)

@router.get("/api/jobs/{job_id}/dashboard", response_class=HTMLResponse)
def view_dashboard(request:Request,job_id:int):
    require_user(request); j=db.get_job(job_id)
    if not j or not j.get("dashboard_path") or not Path(j["dashboard_path"]).exists():
        raise HTTPException(404,"Dashboard not available yet")
    return HTMLResponse(Path(j["dashboard_path"]).read_text(encoding="utf-8"))

@router.get("/api/dashboard/summary")
def dashboard_summary(request:Request):
    require_user(request)
    jobs=db.list_jobs(limit=200)
    completed=[j for j in jobs if j["status"]=="COMPLETED"]
    total_input=sum(j.get("row_count") or 0 for j in completed)
    total_output=sum(j.get("output_rows") or 0 for j in completed)
    total_issues=sum(j.get("issue_count") or 0 for j in completed)
    confidences=[j["confidence"] for j in completed if j.get("confidence") is not None]
    engine_counts={}
    for j in completed:
        engine_counts[j.get("engine") or "UNKNOWN"]=engine_counts.get(j.get("engine") or "UNKNOWN",0)+1
    status_counts={}
    for j in jobs:
        status_counts[j["status"]]=status_counts.get(j["status"],0)+1
    return {
        "total_jobs":len(jobs),
        "completed_jobs":len(completed),
        "total_input_rows":total_input,
        "total_output_rows":total_output,
        "total_issues":total_issues,
        "avg_confidence":round(sum(confidences)/len(confidences),3) if confidences else 0,
        "engine_counts":engine_counts,
        "status_counts":status_counts,
        "recent":jobs[:10],
    }

@router.get("/api/health")
def health(): return {"status":"ok","csi_configured":bool(settings.csi_llm_api_key and "<YOUR_API_KEY>" not in settings.csi_llm_api_key),"polars_threshold_bytes":settings.polars_max_bytes}
