# models/invoice.py

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class Invoice:

    # ── Source 
    source_file: Optional[Path] = None

    # ── Vendor 
    vendor_name:              Optional[str]   = None
    vendor_address:           Optional[str]   = None
    vendor_address_recipient: Optional[str]   = None
    vendor_tax_id:            Optional[str]   = None

    # ── Customer 
    customer_name:               Optional[str] = None
    customer_id:                 Optional[str] = None
    customer_address:            Optional[str] = None
    customer_address_recipient:  Optional[str] = None
    customer_tax_id:             Optional[str] = None

    # ── Invoice info 
    invoice_id:     Optional[str] = None
    purchase_order: Optional[str] = None
    kvk_number:     Optional[str] = None
    payment_term:   Optional[str] = None

    # ── Dates 
    invoice_date:      Optional[str] = None
    due_date:          Optional[str] = None
    service_start_date:Optional[str] = None
    service_end_date:  Optional[str] = None

    # ── Amounts 
    subtotal:               Optional[float] = None
    total_discount:         Optional[float] = None
    tax_amount:             Optional[float] = None
    total_amount:           Optional[float] = None
    amount_due:             Optional[float] = None
    previous_unpaid_balance:Optional[float] = None
    currency:               Optional[str]   = None

    # ── Addresses 
    billing_address:             Optional[str] = None
    billing_address_recipient:   Optional[str] = None
    shipping_address:            Optional[str] = None
    shipping_address_recipient:  Optional[str] = None
    remittance_address:          Optional[str] = None
    remittance_address_recipient:Optional[str] = None
    service_address:             Optional[str] = None
    service_address_recipient:   Optional[str] = None

    # ── Line items 
    items:           list = field(default_factory=list)
    payment_details: list = field(default_factory=list)
    tax_details:     list = field(default_factory=list)

    # ── Classification 
    expense_category: Optional[str] = None
    llm_confidence:   Optional[str] = None

    # ── AI Pipeline Traceability ──────────────────────────
    dit_confidence:  Optional[float] = None  # DiT model score (0 to 1)
    dit_label:       Optional[str]  = None  # "INVOICE" or "NON_INVOICE"
    dit_is_invoice:  Optional[bool] = None  # True if invoice detected
    llm_email_label: Optional[str]  = None

    # ── Processing metadata 
    attempt_count: int = 0

    # ── Validation 
    is_valid:            Optional[bool] = None
    validation_errors:   list = field(default_factory=list)
    validation_warnings: list = field(default_factory=list)

    def to_dict(self) -> dict:
        items_str = ""
        if self.items:
            parts = []
            for it in self.items:
                desc = it.get("description") or ""
                qty  = it.get("quantity")
                up   = it.get("unit_price")
                amt  = it.get("amount")
                part = desc
                if qty is not None:
                    part += f" x{qty}"
                if up is not None:
                    part += f" @ {up}"
                if amt is not None:
                    part += f" = {amt}"
                parts.append(part)
            items_str = " | ".join(parts)

        # Détails paiement → IBAN / SWIFT / numéro de compte
        payment_str = ""
        if self.payment_details:
            pp = []
            for p in self.payment_details:
                if p.get("iban"):
                    pp.append(f"IBAN:{p['iban']}")
                if p.get("swift"):
                    pp.append(f"SWIFT:{p['swift']}")
                if p.get("bank_account_number"):
                    pp.append(f"Account:{p['bank_account_number']}")
            payment_str = " | ".join(pp)

        # Détails TVA
        tax_details_str = ""
        if self.tax_details:
            tax_details_str = " | ".join(
                f"{t.get('rate','')} → {t.get('amount','')}"
                for t in self.tax_details
            )

        return {
            # ── Fournisseur ──────────────────────────────
            "Vendor":                     self.vendor_name,
            "Vendor Address":             self.vendor_address,
            "Vendor Address Recipient":   self.vendor_address_recipient,
            "Vendor Tax ID":              self.vendor_tax_id,

            # ── Client ───────────────────────────────────
            "Customer":                   self.customer_name,
            "Customer ID":                self.customer_id,
            "Customer Address":           self.customer_address,
            "Customer Address Recipient": self.customer_address_recipient,
            "Customer Tax ID":            self.customer_tax_id,

            # ── Infos facture ─────────────────────────────
            "Invoice ID":                 self.invoice_id,
            "Purchase Order":             self.purchase_order,
            "KVK Number":                 self.kvk_number,
            "Payment Term":               self.payment_term,

            # ── Dates ─────────────────────────────────────
            "Invoice Date":               self.invoice_date,
            "Due Date":                   self.due_date,
            "Service Start Date":         self.service_start_date,
            "Service End Date":           self.service_end_date,

            # ── Montants ──────────────────────────────────
            "Subtotal":                   self.subtotal,
            "Tax":                        self.tax_amount,
            "Discount":                   self.total_discount,
            "Total":                      self.total_amount,
            "Amount Due":                 self.amount_due,
            "Previous Unpaid Balance":    self.previous_unpaid_balance,
            "Currency":                   self.currency,
            "Tax Details":                tax_details_str or None,

            # ── Adresses ──────────────────────────────────
            "Billing Address":            self.billing_address,
            "Billing Address Recipient":  self.billing_address_recipient,
            "Shipping Address":           self.shipping_address,
            "Shipping Address Recipient": self.shipping_address_recipient,
            "Remittance Address":         self.remittance_address,
            "Service Address":            self.service_address,

            # ── Paiement ──────────────────────────────────
            "Payment Details":            payment_str or None,

            # ── Lignes de détail ──────────────────────────
            "Line Items":                 items_str or None,

            # ── Classification ────────────────────────────
            "Category":                   self.expense_category,

            # ── Traçabilité IA ────────────────────────────
            "LLM Confidence":             self.llm_confidence,
            "DiT Score":                  round(self.dit_confidence, 3)
                                          if self.dit_confidence else None,
            "DiT Label":                  self.dit_label,
            "LLM Email Label":            self.llm_email_label,
            "Attempts":                   self.attempt_count,
            "Validation Warnings":        "; ".join(self.validation_warnings)
                                          if self.validation_warnings else None,
        }