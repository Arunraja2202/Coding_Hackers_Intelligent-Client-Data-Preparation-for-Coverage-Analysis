from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"

class Settings(BaseSettings):
    app_name: str = "CSI Smart Shipment Transformer"
    secret_key: str = "change-this-in-production"
    admin_username: str = "admin"
    admin_password: str = "ChangeMe123!"
    csi_llm_enabled: bool = True
    csi_llm_endpoint: str = "https://llm-api-cis.azure-intlsd-np.nielsencsp.net/"
    csi_llm_api_key: str = ""
    csi_llm_model: str = "hack-fest-gpt-5.6-luna"
    csi_llm_api_version: str = "2025-03-01-preview"
    csi_llm_timeout_seconds: int = 180
    max_upload_gb: float = 20.0
    polars_max_bytes: int = 1073741824
    spark_master: str = "local[*]"
    spark_driver_memory: str = "4g"
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore", case_sensitive=False)

settings = Settings()

for d in [DATA / "uploads", DATA / "outputs", DATA / "errors", DATA / "reports", DATA / "templates"]:
    d.mkdir(parents=True, exist_ok=True)
