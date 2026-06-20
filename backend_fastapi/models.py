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

    # ── Vendor ────────────────────────────────────────────
    vendor_name                  = Column(String(255), default="")
    vendor_address               = Column(Text, default="")
    vendor_address_recipient     = Column(String(255), default="")
    vendor_tax_id                = Column(String(100), default="")

    # ── Customer ──────────────────────────────────────────
    customer_name                = Column(String(255), default="")
    customer_id                  = Column(String(100), default="")
    customer_address             = Column(Text, default="")
    customer_address_recipient   = Column(String(255), default="")
    customer_tax_id              = Column(String(100), default="")

    # ── Invoice info ──────────────────────────────────────
    invoice_id                   = Column(String(100), default="")
    purchase_order               = Column(String(100), default="")
    kvk_number                   = Column(String(50), default="")
    payment_term                 = Column(String(100), default="")

    # ── Dates ─────────────────────────────────────────────
    invoice_date                 = Column(String(20), default="")
    due_date                     = Column(String(20), default="")
    service_start_date           = Column(String(20), default="")
    service_end_date             = Column(String(20), default="")

    # ── Amounts ───────────────────────────────────────────
    subtotal                     = Column(Float, nullable=True)
    total_discount               = Column(Float, nullable=True)
    tax_amount                   = Column(Float, nullable=True)
    total_amount                 = Column(Float, nullable=True)
    amount_due                   = Column(Float, nullable=True)
    previous_unpaid_balance      = Column(Float, nullable=True)
    currency                     = Column(String(10), default="MAD")

    # ── Addresses ─────────────────────────────────────────
    billing_address              = Column(Text, default="")
    billing_address_recipient    = Column(String(255), default="")
    shipping_address             = Column(Text, default="")
    shipping_address_recipient   = Column(String(255), default="")
    remittance_address           = Column(Text, default="")
    remittance_address_recipient = Column(String(255), default="")
    service_address              = Column(Text, default="")
    service_address_recipient    = Column(String(255), default="")

    # ── Classification ────────────────────────────────────
    expense_category    = Column(String(100), default="Other")

    # ── AI pipeline (internal) ────────────────────────────
    dit_confidence      = Column(Float, nullable=True)
    dit_label           = Column(String(50), default="")
    dit_is_invoice      = Column(Boolean, default=True)
    llm_confidence      = Column(String(20), default="")
    is_valid            = Column(Boolean, default=False)
    validation_errors   = Column(JSON, default=list)
    validation_warnings = Column(JSON, default=list)
    attempt_count       = Column(Integer, default=1)

    # ── Metadata ──────────────────────────────────────────
    status              = Column(String(20), default="need_review")
    source_filename     = Column(String(255), default="")
    source              = Column(String(20), default="upload")
    content_hash        = Column(String(32), default="")
    excel_file          = Column(String(500), default="")
    document_file       = Column(String(500), default="")
    created_at          = Column(DateTime, default=datetime.utcnow)
