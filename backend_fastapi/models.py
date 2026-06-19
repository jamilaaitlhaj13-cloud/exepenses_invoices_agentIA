# backend_fastapi/models.py
from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Float, JSON, Text
from database import Base

INDUSTRY_CHOICES = [
    "tech","finance","healthcare","retail",
    "manufacturing","consulting","education",
    "real_estate","transport","other"
]

INDUSTRY_LABELS = {
    "tech":          "Technology / IT",
    "finance":       "Finance & Banking",
    "healthcare":    "Healthcare",
    "retail":        "Retail & Distribution",
    "manufacturing": "Manufacturing",
    "consulting":    "Consulting & Services",
    "education":     "Education",
    "real_estate":   "Real Estate",
    "transport":     "Transport & Logistics",
    "other":         "Other",
}

class Company(Base):
    __tablename__ = "companies"

    id           = Column(Integer, primary_key=True, index=True)
    email        = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    company_name = Column(String(200), nullable=False)
    industry     = Column(String(50), default="other")
    phone        = Column(String(20), default="")
    country      = Column(String(100), default="Maroc")
    city         = Column(String(100), default="")
    rc_number    = Column(String(50), default="")
    created_at   = Column(DateTime, default=datetime.utcnow)

    # Email verification
    is_email_verified = Column(Boolean, default=False)
    verification_code = Column(String(6), default="")
    code_expires_at   = Column(DateTime, nullable=True)


class InvoiceRecord(Base):
    __tablename__ = "invoice_records"

    id                  = Column(Integer, primary_key=True, index=True)
    company_id          = Column(Integer, nullable=False, index=True)
    vendor_name         = Column(String(255), default="")
    invoice_date        = Column(String(20), default="")
    invoice_id          = Column(String(100), default="")
    total_amount        = Column(Float, nullable=True)
    subtotal            = Column(Float, nullable=True)
    tax_amount          = Column(Float, nullable=True)
    currency            = Column(String(10), default="MAD")
    expense_category    = Column(String(100), default="Other")
    dit_confidence      = Column(Float, nullable=True)
    dit_label           = Column(String(50), default="")
    dit_is_invoice      = Column(Boolean, default=True)
    llm_confidence      = Column(String(20), default="")
    is_valid            = Column(Boolean, default=False)
    validation_errors   = Column(JSON, default=list)
    validation_warnings = Column(JSON, default=list)
    attempt_count       = Column(Integer, default=1)
    status              = Column(String(20), default="need_review")
    source_filename     = Column(String(255), default="")
    source              = Column(String(20), default="upload")
    content_hash        = Column(String(32), default="")
    excel_file          = Column(String(500), default="")
    document_file       = Column(String(500), default="")
    created_at          = Column(DateTime, default=datetime.utcnow)
