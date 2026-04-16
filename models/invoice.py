from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class Invoice:
    """
    Represents an invoice that travels through the pipeline.
    Attributes match exactly the fields returned by
    Azure Document Intelligence prebuilt-invoice model.
    """

    # ── Filled by MailFetcherTool ──────────────────────────
    source_file: Optional[Path] = None

    # ── Vendor information ─────────────────────────────────
    vendor_name:               Optional[str] = None  # VendorName
    vendor_address:            Optional[str] = None  # VendorAddress
    vendor_address_recipient:  Optional[str] = None  # VendorAddressRecipient
    vendor_tax_id:             Optional[str] = None  # VendorTaxId

    # ── Customer information ───────────────────────────────
    customer_name:              Optional[str] = None  # CustomerName
    customer_id:                Optional[str] = None  # CustomerId
    customer_address:           Optional[str] = None  # CustomerAddress
    customer_address_recipient: Optional[str] = None  # CustomerAddressRecipient
    customer_tax_id:            Optional[str] = None  # CustomerTaxId

    # ── References ─────────────────────────────────────────
    invoice_id:     Optional[str] = None  # InvoiceId
    purchase_order: Optional[str] = None  # PurchaseOrder
    kvk_number:     Optional[str] = None  # KVKNumber

    # ── Dates ──────────────────────────────────────────────
    invoice_date:       Optional[str] = None  # InvoiceDate       (YYYY-MM-DD)
    due_date:           Optional[str] = None  # DueDate           (YYYY-MM-DD)
    service_start_date: Optional[str] = None  # ServiceStartDate  (YYYY-MM-DD)
    service_end_date:   Optional[str] = None  # ServiceEndDate    (YYYY-MM-DD)

    # ── Amounts ────────────────────────────────────────────
    subtotal:                Optional[float] = None  # SubTotal
    total_discount:          Optional[float] = None  # TotalDiscount
    tax_amount:              Optional[float] = None  # TotalTax
    total_amount:            Optional[float] = None  # InvoiceTotal
    amount_due:              Optional[float] = None  # AmountDue
    previous_unpaid_balance: Optional[float] = None  # PreviousUnpaidBalance
    currency:                str             = "MAD" # CurrencyCode

    # ── Addresses ──────────────────────────────────────────
    billing_address:              Optional[str] = None  # BillingAddress
    billing_address_recipient:    Optional[str] = None  # BillingAddressRecipient
    shipping_address:             Optional[str] = None  # ShippingAddress
    shipping_address_recipient:   Optional[str] = None  # ShippingAddressRecipient
    remittance_address:           Optional[str] = None  # RemittanceAddress
    remittance_address_recipient: Optional[str] = None  # RemittanceAddressRecipient
    service_address:              Optional[str] = None  # ServiceAddress
    service_address_recipient:    Optional[str] = None  # ServiceAddressRecipient

    # ── Payment ────────────────────────────────────────────
    payment_term: Optional[str] = None  # PaymentTerm

    # ── Payment details (list) ─────────────────────────────
    # Each element: {iban, bank_account_number,
    #                bpay_biller_code, bpay_reference, swift}
    payment_details: list = field(default_factory=list)

    # ── Tax details (list) ─────────────────────────────────
    # Each element: {amount, rate}
    tax_details: list = field(default_factory=list)

    # ── Installment payments (list) ────────────────────────
    # Each element: {amount, due_date}
    paid_in_four_installments: list = field(default_factory=list)

    # ── Line items (list) ──────────────────────────────────
    # Each element: {amount, date, description, quantity,
    #                product_code, tax, tax_rate, unit, unit_price}
    items: list = field(default_factory=list)

    # ── Filled by AIClassifierTool ─────────────────────────
    expense_category: Optional[str] = None  # SaaS | Travel | Office | Utilities | Other
    llm_confidence:   Optional[str] = None  # high | medium | low

    # ── OCR confidence scores (per field) ──────────────────
    confidence_scores: dict = field(default_factory=dict)

    # ── Filled by ValidationTool ───────────────────────────
    is_valid:          Optional[bool] = None
    validation_errors: list           = field(default_factory=list)

    # ── Pipeline tracking ──────────────────────────────────
    attempt_count: int = 0

    def to_dict(self) -> dict:
        """
        Converts the invoice to a dictionary for Excel export.
        Each key becomes a column in the output spreadsheet.
        """
        return {
            # Vendor
            "Vendor":           self.vendor_name,
            "Vendor Address":   self.vendor_address,
            "Vendor Tax ID":    self.vendor_tax_id,

            # Customer
            "Customer":         self.customer_name,
            "Customer Address": self.customer_address,
            "Customer Tax ID":  self.customer_tax_id,

            # References
            "Invoice ID":       self.invoice_id,
            "Purchase Order":   self.purchase_order,

            # Dates
            "Invoice Date":     self.invoice_date,
            "Due Date":         self.due_date,
            "Service Start":    self.service_start_date,
            "Service End":      self.service_end_date,

            # Amounts
            "Subtotal":         self.subtotal,
            "Discount":         self.total_discount,
            "Tax":              self.tax_amount,
            "Total":            self.total_amount,
            "Amount Due":       self.amount_due,
            "Currency":         self.currency,

            # Classification
            "Category":         self.expense_category,

            # Line items count
            "Line Items":       len(self.items),

            # Source file
            "Source File":      self.source_file.name if self.source_file else None,
        }

    def __repr__(self) -> str:
        return (
            f"Invoice("
            f"vendor='{self.vendor_name}', "
            f"date='{self.invoice_date}', "
            f"total={self.total_amount} {self.currency}, "
            f"category='{self.expense_category}', "
            f"valid={self.is_valid})"
        )