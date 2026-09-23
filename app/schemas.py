from pydantic import BaseModel, Field
from typing import Any

TARGET_COLUMNS = ["Country","Region","Channel","City/State","Category","Brand","SKU","Fact"]

class TransformRequest(BaseModel):
    required_columns: list[str] = Field(default=TARGET_COLUMNS)
    template_name: str | None = None

class LoginRequest(BaseModel):
    username: str
    password: str
