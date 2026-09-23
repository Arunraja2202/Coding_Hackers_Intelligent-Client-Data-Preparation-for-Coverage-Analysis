import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import db
from app.config import settings
from app.services.security import hash_password

db.init_db(); db.upsert_user(settings.admin_username,hash_password(settings.admin_password)); print(f"Admin ready: {settings.admin_username}")
