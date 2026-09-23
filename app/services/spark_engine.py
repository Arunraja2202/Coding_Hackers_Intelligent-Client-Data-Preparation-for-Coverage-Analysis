from pathlib import Path
import shutil
from .transformer import is_period_column, normalize_period
from app.schemas import TARGET_COLUMNS

def run_spark(path, plan, required_columns, output_path):
    from pyspark.sql import SparkSession, functions as F
    from .jobs import _load_table_polars
    spark=(SparkSession.builder.appName("CSI-Smart-Transformer").master("local[*]").config("spark.driver.memory","4g").getOrCreate())
    try:
        ext=Path(path).suffix.lower()
        source=str(path)
        if ext in {".csv",".tsv",".txt"}:
            sep="\t" if ext==".tsv" else ","
            sdf=spark.read.option("header",True).option("inferSchema",True).option("sep",sep).csv(source)
        elif ext==".parquet": sdf=spark.read.parquet(source)
        elif ext in {".xlsx",".xls"}:
            # Excel is streamed to CSV first, then Spark performs the large-data work.
            from .workbook import xlsx_to_csv
            sheet=(plan.get("sheet_plans") or [{"sheet":"Sheet1"}])[0].get("sheet")
            header=int((plan.get("sheet_plans") or [{"header_row":1}])[0].get("header_row",1))
            tmp=xlsx_to_csv(Path(path),sheet,header); sdf=spark.read.option("header",True).option("inferSchema",True).csv(str(tmp)); tmp.unlink(missing_ok=True)
        else:
            # JSON/XML can be normalized before Spark; these formats are generally not line-oriented tabular data.
            pdf=_load_table_polars(Path(path)); tmp=str(Path(path).with_suffix(".spark_input.csv")); pdf.write_csv(tmp); sdf=spark.read.option("header",True).option("inferSchema",True).csv(tmp)
        for c,t in sdf.dtypes:
            if t=="string": sdf=sdf.withColumn(c,F.trim(F.col(c)))
        sdf=sdf.na.drop("all").dropDuplicates()
        mapping=plan.get("mapping",{})
        selected=[c for c in required_columns if c in TARGET_COLUMNS]
        expr=[]
        for target in selected:
            src=mapping.get(target)
            expr.append(F.col(src).alias(target) if src and src in sdf.columns else F.lit(None).alias(target))
        for c in sdf.columns:
            if is_period_column(c): expr.append(F.col(c).alias(normalize_period(c)))
        out=sdf.select(*expr)
        output_path=Path(output_path).with_suffix(".csv")
        tmp_dir=str(output_path)+".tmp"
        out.coalesce(1).write.mode("overwrite").option("header",True).csv(tmp_dir)
        part=next(Path(tmp_dir).glob("part-*.csv"),None)
        if not part: raise RuntimeError("Spark produced no output part")
        output_path.unlink(missing_ok=True); shutil.move(str(part),str(output_path)); shutil.rmtree(tmp_dir,ignore_errors=True)
        count=out.count()
        spark.stop(); return str(output_path),count
    except Exception:
        spark.stop(); raise
