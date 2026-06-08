# backend_fastapi/schemas.py
from typing import Optional, List, Any
from pydantic import BaseModel, EmailStr
from datetime import datetime

# ── Auth ──────────────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    email:        EmailStr
    password:     str
    password2:    str
    company_name: str
    industry:     str = "other"
    phone:        str = ""
    country:      str = "Maroc"
    city:         str = ""
    rc_number:    str = ""

class LoginRequest(BaseModel):
    email:    EmailStr
    password: str

class TokenResponse(BaseModel):
    access:       str
    refresh:      str
    company_name: str
    company_id:   int
    industry:     Optional[str] = ""

class RefreshRequest(BaseModel):
    refresh: str

class AccessTokenResponse(BaseModel):
    access: str

class ProfileResponse(BaseModel):
    id:           int
    email:        str
    company_name: str
    industry:     str
    phone:        str
    country:      str
    city:         str
    rc_number:    str
    created_at:   datetime

    class Config:
        from_attributes = True

class VerifyEmailRequest(BaseModel):
    email: EmailStr
    code:  str

class SendCodeRequest(BaseModel):
    email: EmailStr

# ── Invoices ──────────────────────────────────────────────────────────────────

class InvoiceCreate(BaseModel):
    vendor_name:         str = ""
    invoice_date:        str = ""
    invoice_id:          str = ""
    total_amount:        Optional[float] = None
    subtotal:            Optional[float] = None
    tax_amount:          Optional[float] = None
    currency:            str = "MAD"
    expense_category:    str = "Other"
    dit_confidence:      Optional[float] = None
    dit_label:           str = ""
    dit_is_invoice:      bool = True
    llm_confidence:      str = ""
    is_valid:            bool = False
    validation_errors:   List[Any] = []
    validation_warnings: List[Any] = []
    attempt_count:       int = 1
    status:              str = "need_review"
    source_filename:     str = ""
    source:              str = "upload"
    content_hash:        str = ""

class InvoiceResponse(BaseModel):
    id:                  int
    vendor_name:         str
    invoice_date:        str
    invoice_id:          str
    total_amount:        Optional[float]
    subtotal:            Optional[float]
    tax_amount:          Optional[float]
    currency:            str
    expense_category:    str
    dit_confidence:      Optional[float]
    dit_label:           str
    dit_is_invoice:      bool
    llm_confidence:      str
    is_valid:            bool
    validation_errors:   List[Any]
    validation_warnings: List[Any]
    attempt_count:       int
    status:              str
    source_filename:     str
    source:              str
    content_hash:        str
    excel_file:          str
    created_at:          datetime

    class Config:
        from_attributes = True
