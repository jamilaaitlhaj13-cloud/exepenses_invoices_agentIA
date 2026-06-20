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
    country:      str = "Morocco"
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
    # Vendor
    vendor_name:                 str = ""
    vendor_address:              str = ""
    vendor_address_recipient:    str = ""
    vendor_tax_id:               str = ""
    # Customer
    customer_name:               str = ""
    customer_id:                 str = ""
    customer_address:            str = ""
    customer_address_recipient:  str = ""
    customer_tax_id:             str = ""
    # Invoice info
    invoice_id:                  str = ""
    purchase_order:              str = ""
    kvk_number:                  str = ""
    payment_term:                str = ""
    # Dates
    invoice_date:                str = ""
    due_date:                    str = ""
    service_start_date:          str = ""
    service_end_date:            str = ""
    # Amounts
    subtotal:                    Optional[float] = None
    total_discount:              Optional[float] = None
    tax_amount:                  Optional[float] = None
    total_amount:                Optional[float] = None
    amount_due:                  Optional[float] = None
    previous_unpaid_balance:     Optional[float] = None
    currency:                    str = "MAD"
    # Addresses
    billing_address:             str = ""
    billing_address_recipient:   str = ""
    shipping_address:            str = ""
    shipping_address_recipient:  str = ""
    remittance_address:          str = ""
    remittance_address_recipient:str = ""
    service_address:             str = ""
    service_address_recipient:   str = ""
    # Classification
    expense_category:            str = "Other"
    # AI pipeline (internal)
    dit_confidence:              Optional[float] = None
    dit_label:                   str = ""
    dit_is_invoice:              bool = True
    llm_confidence:              str = ""
    is_valid:                    bool = False
    validation_errors:           List[Any] = []
    validation_warnings:         List[Any] = []
    attempt_count:               int = 1
    # Metadata
    status:                      str = "need_review"
    source_filename:             str = ""
    source:                      str = "upload"
    content_hash:                str = ""

class InvoiceResponse(BaseModel):
    id:                          int
    # Vendor
    vendor_name:                 str
    vendor_address:              str = ""
    vendor_address_recipient:    str = ""
    vendor_tax_id:               str = ""
    # Customer
    customer_name:               str = ""
    customer_id:                 str = ""
    customer_address:            str = ""
    customer_address_recipient:  str = ""
    customer_tax_id:             str = ""
    # Invoice info
    invoice_id:                  str
    purchase_order:              str = ""
    kvk_number:                  str = ""
    payment_term:                str = ""
    # Dates
    invoice_date:                str
    due_date:                    str = ""
    service_start_date:          str = ""
    service_end_date:            str = ""
    # Amounts
    subtotal:                    Optional[float]
    total_discount:              Optional[float] = None
    tax_amount:                  Optional[float]
    total_amount:                Optional[float]
    amount_due:                  Optional[float] = None
    previous_unpaid_balance:     Optional[float] = None
    currency:                    str
    # Addresses
    billing_address:             str = ""
    billing_address_recipient:   str = ""
    shipping_address:            str = ""
    shipping_address_recipient:  str = ""
    remittance_address:          str = ""
    remittance_address_recipient:str = ""
    service_address:             str = ""
    service_address_recipient:   str = ""
    # Classification
    expense_category:            str
    # AI pipeline (internal)
    dit_confidence:              Optional[float]
    dit_label:                   str
    dit_is_invoice:              bool
    llm_confidence:              str
    is_valid:                    bool
    validation_errors:           List[Any]
    validation_warnings:         List[Any]
    attempt_count:               int
    # Metadata
    status:                      str
    source_filename:             str
    source:                      str
    content_hash:                str
    excel_file:                  str
    document_file:               Optional[str] = ""
    created_at:                  datetime

    class Config:
        from_attributes = True
