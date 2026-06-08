# backend_fastapi/routers/auth.py
import os
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
from models import Company, INDUSTRY_LABELS
from schemas import (
    RegisterRequest, LoginRequest, ProfileResponse,
    RefreshRequest, SendCodeRequest, VerifyEmailRequest
)
from auth_utils import (
    hash_password, verify_password,
    create_access_token, create_refresh_token,
    decode_token, get_current_company, generate_code
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register/")
def register(data: RegisterRequest, db: Session = Depends(get_db)):
    if data.password != data.password2:
        raise HTTPException(400, detail={"password": ["Passwords do not match."]})
    if len(data.password) < 8:
        raise HTTPException(400, detail={"password": ["Min 8 characters."]})
    if db.query(Company).filter(Company.email == data.email.lower()).first():
        raise HTTPException(400, detail={"email": ["Email already registered."]})

    company = Company(
        email=data.email.lower(),
        hashed_password=hash_password(data.password),
        company_name=data.company_name,
        industry=data.industry,
        phone=data.phone,
        country=data.country,
        city=data.city,
        rc_number=data.rc_number,
    )
    db.add(company)
    db.commit()
    db.refresh(company)
    return {
        "message":      "Compte cree avec succes.",
        "company_name": company.company_name,
        "company_id":   company.id,
        "access":       create_access_token(company.id),
        "refresh":      create_refresh_token(company.id),
    }


@router.post("/login/")
def login(data: LoginRequest, db: Session = Depends(get_db)):
    company = db.query(Company).filter(Company.email == data.email.lower()).first()
    if not company or not verify_password(data.password, company.hashed_password):
        raise HTTPException(401, detail={"error": "Email ou mot de passe incorrect."})
    return {
        "company_name": company.company_name,
        "company_id":   company.id,
        "industry":     INDUSTRY_LABELS.get(company.industry, company.industry),
        "access":       create_access_token(company.id),
        "refresh":      create_refresh_token(company.id),
    }


@router.post("/refresh/")
def refresh_token(data: RefreshRequest, db: Session = Depends(get_db)):
    payload = decode_token(data.refresh)
    if payload.get("type") != "refresh":
        raise HTTPException(401, detail="Invalid token type")
    return {"access": create_access_token(int(payload["sub"]))}


@router.get("/profile/")
def get_profile(company: Company = Depends(get_current_company)):
    return ProfileResponse.model_validate(company)


@router.post("/send-verification/")
def send_verification(data: SendCodeRequest, db: Session = Depends(get_db)):
    company = db.query(Company).filter(Company.email == data.email.lower()).first()
    if not company:
        return {"message": "If this email exists, a code has been sent."}
    if company.is_email_verified:
        return {"message": "Email already verified."}
    code = generate_code()
    company.verification_code = code
    company.code_expires_at   = datetime.utcnow() + timedelta(minutes=15)
    db.commit()
    _send_email(company.email, company.company_name, code)
    response = {"message": "Verification code sent."}
    if os.getenv("DEBUG", "True") == "True":
        response["debug_code"] = code
    return response


@router.post("/verify-email/")
def verify_email(data: VerifyEmailRequest, db: Session = Depends(get_db)):
    company = db.query(Company).filter(Company.email == data.email.lower()).first()
    if not company:
        raise HTTPException(400, detail={"error": "Invalid email."})
    if company.is_email_verified:
        return {"message": "Already verified."}
    if not company.verification_code:
        raise HTTPException(400, detail={"error": "No code found."})
    if datetime.utcnow() > company.code_expires_at:
        raise HTTPException(400, detail={"error": "Code expired."})
    if company.verification_code != data.code:
        raise HTTPException(400, detail={"error": "Invalid code."})
    company.is_email_verified = True
    company.verification_code = ""
    company.code_expires_at   = None
    db.commit()
    return {"message": "Email verified successfully."}


def _send_email(to_email: str, company_name: str, code: str):
    import smtplib
    from email.mime.text import MIMEText
    user = os.getenv("USER_EMAIL", "")
    pwd  = os.getenv("EMAIL_PASS", "")
    if not user or not pwd:
        return
    try:
        msg = MIMEText(
            f"Hello {company_name},\n\nYour verification code is: {code}\n\n"
            f"Valid for 15 minutes.\n\n-- SmartExpenseAgent"
        )
        msg["Subject"] = "SmartExpenseAgent - Verification code"
        msg["From"]    = user
        msg["To"]      = to_email
        with smtplib.SMTP("smtp.office365.com", 587) as s:
            s.starttls()
            s.login(user, pwd)
            s.send_message(msg)
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Email error: {e}")
