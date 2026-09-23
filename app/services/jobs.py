import json, time, traceback
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import polars as pl
from app.config import settings, DATA
from app import db
from .profiling import choose_engine, profile_polars, sample_file_metadata
from .llm import CSIClient
from .cleaning import clean_records
from .transformer import transform_records, transform_matrix, write_output
from .workbook import xlsx_to_csv
from . import reporting

EXECUTOR=ThreadPoolExecutor(max_workers=2)

def submit(job_id, required_columns, template_name=None):
    EXECUTOR.submit(process_job,job_id,required_columns,template_name)

def _load_table_polars(path,sheet=None,header_row=1):
    ext=path.suffix.lower()
    if ext in {".csv",".tsv",".txt"}:
        sep="\t" if ext==".tsv" else ","
        return pl.read_csv(path,separator=sep,infer_schema_length=10000,try_parse_dates=False)
    if ext==".parquet": return pl.read_parquet(path)
    if ext in {".xlsx",".xls"}:
        if ext==".xlsx":
            tmp=xlsx_to_csv(path,sheet or "Sheet1",header_row)
            df=pl.read_csv(tmp,infer_schema_length=10000,try_parse_dates=False)
            Path(tmp).unlink(missing_ok=True); return df
        # XLS is converted through xlrd into rows and then into Polars.
        import xlrd
        book=xlrd.open_workbook(path,on_demand=True); sh=book.sheet_by_name(sheet) if sheet else book.sheet_by_index(0)
        rows=[sh.row_values(i) for i in range(max(0,header_row-1),sh.nrows)]
        if not rows:return pl.DataFrame()
        headers=[]; seen={}
        for j,v in enumerate(rows[0]):
            h=str(v).strip() if v not in (None,"") else f"Column_{j+1}"; seen[h]=seen.get(h,0)+1; headers.append(h if seen[h]==1 else f"{h}_{seen[h]}")
        return pl.DataFrame([dict(zip(headers,r)) for r in rows[1:]],strict=False)
    if ext==".json":
        raw=json.loads(path.read_text(encoding="utf-8")); rows=raw if isinstance(raw,list) else raw.get("data",raw.get("rows",[raw])) if isinstance(raw,dict) else []
        return pl.from_dicts(rows,strict=False) if rows else pl.DataFrame()
    if ext==".xml":
        import xml.etree.ElementTree as ET
        root=ET.parse(path).getroot(); rows=[]
        for e in list(root): rows.append({c.tag.split("}")[-1]:c.text for c in list(e)})
        return pl.from_dicts(rows,strict=False) if rows else pl.DataFrame()
    raise ValueError(f"Unsupported extension {ext}")

def _matrix_rows(path,sheet):
    import openpyxl
    wb=openpyxl.load_workbook(path,read_only=True,data_only=True); ws=wb[sheet]
    rows=[list(r) for r in ws.iter_rows(values_only=True)]
    wb.close(); return rows

def process_job(job_id,required_columns,template_name=None):
    job=db.get_job(job_id); path=Path(job["stored_path"])
    out_path=DATA/"outputs"/f"job_{job_id}_cleaned.xlsx"; err_path=DATA/"errors"/f"job_{job_id}_issues.csv"; report_path=DATA/"reports"/f"job_{job_id}_report.json"
    started=time.perf_counter(); db.update_job(job_id,status="RUNNING",progress=5,stage="Profiling",started_at=db.now())
    try:
        engine=choose_engine(path,settings.polars_max_bytes); db.update_job(job_id,engine=engine,progress=10,stage="Analyzing structure")
        snapshot=sample_file_metadata(path)
        db.update_job(job_id,progress=20,stage="Calling CSI LLM")
        plan=CSIClient().complete_plan(snapshot,required_columns)
        llm_mode=plan.get("mode","CSI_LLM"); confidence=float(plan.get("confidence",0))
        db.update_job(job_id,llm_mode=llm_mode,confidence=confidence,progress=35,stage="Cleaning and transforming")
        all_output=[]; all_issues=[]; input_rows=0; null_count=0
        ext=path.suffix.lower()
        matrix_enabled=bool((plan.get("matrix_strategy") or {}).get("enabled")) or plan.get("dataset_mode")=="matrix"
        if engine == "PYSPARK":
            from .spark_engine import run_spark
            spark_out, spark_count = run_spark(path, plan, required_columns, out_path)
            out_path = Path(spark_out)
            input_rows = spark_count
            all_output = []
        elif matrix_enabled and ext in {".xlsx",".xls"}:
            sheets=snapshot.get("sheets",[])
            for sp in sheets:
                if sp["name"].lower()=="guide": continue
                rows=_matrix_rows(path,sp["name"]); input_rows+=max(0,len(rows)-4)
                unit={"KG":"KG","UN":"UN","LIT":"LT"}.get(sp["name"].upper(),sp["name"])
                out,issues=transform_matrix(rows,plan,required_columns,unit); all_output.extend(out); all_issues.extend(issues)
        else:
            sheets=plan.get("sheet_plans") or []
            if ext in {".xlsx",".xls"} and not sheets:
                sheets=[{"sheet":next((s["name"] for s in snapshot["sheets"] if s["name"].lower()!="guide"),snapshot["sheets"][0]["name"]),"header_row":1}]
            if ext not in {".xlsx",".xls"}: sheets=[{"sheet":"data","header_row":1}]
            for sp in sheets:
                sheet=sp.get("sheet") or sp.get("name") or "data"
                if str(sheet).lower()=="guide": continue
                df=_load_table_polars(path,None if sheet=="data" else sheet,int(sp.get("header_row",1)))
                if df.is_empty(): continue
                input_rows+=df.height; null_count+=sum(df[c].null_count() for c in df.columns)
                # Cleaning is row-wise only after Polars ingestion; the data stays in Polars for I/O/processing.
                records=df.to_dicts(); cleaned,clean_issues=clean_records(records)
                out,issues=transform_records(cleaned,plan,required_columns)
                all_output.extend(out); all_issues.extend(clean_issues+issues)
        db.update_job(job_id,progress=75,stage="Writing output")
        if engine != "PYSPARK":
            write_output(all_output,out_path)
        if all_issues:
            with err_path.open("w",encoding="utf-8-sig",newline="") as f:
                import csv; w=csv.DictWriter(f,fieldnames=["source_row","issue_type","detail"]); w.writeheader(); w.writerows(all_issues)
        else: err_path.write_text("source_row,issue_type,detail\n",encoding="utf-8")
        duration=time.perf_counter()-started
        output_rows = (spark_count if engine == "PYSPARK" else len(all_output))
        report={"job_id":job_id,"filename":job["filename"],"engine":engine,"llm_mode":llm_mode,"confidence":confidence,"input_rows":input_rows,"output_rows":output_rows,"null_cells":null_count,"issues":len(all_issues),"required_columns":required_columns,"dataset_mode":plan.get("dataset_mode"),"mapping":plan.get("mapping"),"transformations":plan.get("transformations"),"review":plan.get("review"),"assumptions":plan.get("assumptions"),"fallback_reason":plan.get("fallback_reason"),"duration_seconds":round(duration,3),"guardrails":["source trace retained","explicit zero preserved","signed values preserved","low-confidence mappings flagged","Result/Total rows excluded from atomic output"]}
        report_path.write_text(json.dumps(report,indent=2,default=str),encoding="utf-8")
        db.update_job(job_id,progress=90,stage="Building reconciliation, method note & dashboard")
        artifacts=reporting.generate_all(job,report,plan,all_output,all_issues,input_rows,null_count,DATA)
        db.update_job(job_id,status="COMPLETED",progress=100,stage="Completed",row_count=input_rows,output_rows=output_rows,null_count=null_count,issue_count=len(all_issues),output_path=str(out_path),error_path=str(err_path),report_path=str(report_path),reconciliation_path=artifacts["reconciliation"],method_note_path=artifacts["method_note"],powerbi_path=artifacts["powerbi"],dashboard_path=artifacts["dashboard"],completed_at=db.now())
    except Exception as e:
        traceback.print_exc(); db.update_job(job_id,status="FAILED",progress=100,stage="Failed",error_message=str(e),completed_at=db.now())
