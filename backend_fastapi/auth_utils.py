# backend_fastapi/auth_utils.py
import os, random, string
import bcrypt
from datetime import datetime, timedelta
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from database import get_db
from models import Company

SECRET_KEY      = os.getenv("SECRET_KEY", "fastapi-secret-key-change-in-production")
ALGORITHM       = "HS256"
ACCESS_EXPIRE   = 60 * 8      # 8 hours
REFRESH_EXPIRE  = 60 * 24 * 30  # 30 days

bearer = HTTPBearer()

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))

def create_token(data: dict, expires_minutes: int) -> str:
    payload = data.copy()
    payload["exp"] = datetime.utcnow() + timedelta(minutes=expires_minutes)
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def create_access_token(company_id: int) -> str:
    return create_token({"sub": str(company_id), "type": "access"}, ACCESS_EXPIRE)

def create_refresh_token(company_id: int) -> str:
    return create_token({"sub": str(company_id), "type": "refresh"}, REFRESH_EXPIRE)

def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

def get_current_company(
    credentials: HTTPAuthorizationCredentials = Depends(bearer),
    db: Session = Depends(get_db),
) -> Company:
    payload = decode_token(credentials.credentials)
    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Invalid token type")
    company = db.query(Company).filter(Company.id == int(payload["sub"])).first()
    if not company:
        raise HTTPException(status_code=401, detail="Company not found")
    return company

def generate_code(length: int = 6) -> str:
    return "".join(random.choices(string.digits, k=length))
