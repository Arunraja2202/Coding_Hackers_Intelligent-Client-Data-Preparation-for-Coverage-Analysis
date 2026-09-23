from passlib.context import CryptContext
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from app.config import settings

pwd=CryptContext(schemes=["bcrypt"], deprecated="auto")
serializer=URLSafeTimedSerializer(settings.secret_key, salt="sdtp-session")

def hash_password(p): return pwd.hash(p)
def verify_password(p,h): return pwd.verify(p,h)
def make_session(username): return serializer.dumps({"username":username})
def read_session(token, max_age=86400):
    try: return serializer.loads(token,max_age=max_age).get("username")
    except (BadSignature,SignatureExpired): return None
