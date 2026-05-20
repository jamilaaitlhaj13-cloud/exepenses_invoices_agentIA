# models/invoice.py

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class Invoice:

    # ── Source ────────────────────────────────────────────
    source_file: Optional[Path] = None

    # ── Vendor ───────────────────────────────────────────
    vendor_name:              Optional[str]   = None
    vendor_address:           Optional[str]   = None
    vendor_address_recipient: Optional[str]   = None
    vendor_tax_id:            Optional[str]   = None

    # ── Customer ──────────────────────────────────────────
    customer_name:               Optional[str] = None
    customer_id:                 Optional[str] = None
    customer_address:            Optional[str] = None
    customer_address_recipient:  Optional[str] = None
    customer_tax_id:             Optional[str] = None

    # ── Invoice info ──────────────────────────────────────
    invoice_id:     Optional[str] = None
    purchase_order: Optional[str] = None
    kvk_number:     Optional[str] = None
    payment_term:   Optional[str] = None

    # ── Dates ─────────────────────────────────────────────
    invoice_date:      Optional[str] = None
    due_date:          Optional[str] = None
    service_start_date:Optional[str] = None
    service_end_date:  Optional[str] = None

    # ── Amounts ───────────────────────────────────────────
    subtotal:               Optional[float] = None
    total_discount:         Optional[float] = None
    tax_amount:             Optional[float] = None
    total_amount:           Optional[float] = None
    amount_due:             Optional[float] = None
    previous_unpaid_balance:Optional[float] = None
    currency:               Optional[str]   = None

    # ── Addresses ─────────────────────────────────────────
    billing_address:             Optional[str] = None
    billing_address_recipient:   Optional[str] = None
    shipping_address:            Optional[str] = None
    shipping_address_recipient:  Optional[str] = None
    remittance_address:          Optional[str] = None
    remittance_address_recipient:Optional[str] = None
    service_address:             Optional[str] = None
    service_address_recipient:   Optional[str] = None

    # ── Line items ────────────────────────────────────────
    items:           list = field(default_factory=list)
    payment_details: list = field(default_factory=list)
    tax_details:     list = field(default_factory=list)

    # ── Classification ────────────────────────────────────
    expense_category: Optional[str] = None
    llm_confidence:   Optional[str] = None

    # ── AI Pipeline Traceability ──────────────────────────
    dit_confidence:  Optional[float] = None  # DiT model score (0 to 1)
    dit_label:       Optional[str]  = None  # "INVOICE" or "NON_INVOICE"
    dit_is_invoice:  Optional[bool] = None  # True if invoice detected
    llm_email_label: Optional[str]  = None

    # ── Processing metadata ───────────────────────────────
    attempt_count: int = 0

    # ── Validation ────────────────────────────────────────
    is_valid:            Optional[bool] = None
    validation_errors:   list = field(default_factory=list)
    validation_warnings: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "Vendor":          self.vendor_name,
            "Customer":        self.customer_name,
            "Invoice ID":      self.invoice_id,
            "Invoice Date":    self.invoice_date,
            "Due Date":        self.due_date,
            "Purchase Order":  self.purchase_order,
            "Payment Term":    self.payment_term,
            "Subtotal":        self.subtotal,
            "Tax":             self.tax_amount,
            "Discount":        self.total_discount,
            "Total":           self.total_amount,
            "Amount Due":      self.amount_due,
            "Currency":        self.currency,
            "Category":        self.expense_category,
            # ── AI Traceability ─────────────────────────
            "LLM Confidence":  self.llm_confidence,
            "DiT Score":       round(self.dit_confidence, 3)
                               if self.dit_confidence else None,
            "DiT Label":       self.dit_label,
            "LLM Email Label": self.llm_email_label,
        }