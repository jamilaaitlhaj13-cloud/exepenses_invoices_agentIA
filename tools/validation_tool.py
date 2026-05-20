import logging
import re
from datetime import datetime, date
from models.invoice import Invoice
from models.validation_result import ValidationResult

logger = logging.getLogger(__name__)
MATH_TOLERANCE = 0.02                    
OCR_MATH_TOLERANCE_PCT = 0.05           
DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
VALID_CURRENCIES = {"MAD", "EUR", "USD", "GBP", "CHF", "AED"}

# Only these fields BLOCK validation if missing
REQUIRED_FIELDS = {
    "vendor_name":  "Vendor name",
    "invoice_date": "Invoice date",
    "total_amount": "Total amount",
}

# These fields generate a WARNING if missing 
RECOMMENDED_FIELDS = {
    "customer_name": "Customer name",
    "tax_amount":    "Tax amount",
    "due_date":      "Due date",
    "currency":      "Currency",
    "invoice_id":    "Invoice ID",
}
class ValidationTool:

    def validate(self, invoice: Invoice) -> ValidationResult:
        """Validate the consistency of invoice data.
        Only REQUIRED_FIELDS block validation.
        Other rules generate warnings.
        """
        result = ValidationResult(is_valid=True)

        # ── Blocking rules (only missing required fields) ──
        self._check_required_fields(invoice, result)
        self._check_date(invoice, result)

        # ── Non-blocking rules (warnings only) ─────────────
        self._check_amounts(invoice, result)
        self._check_math(invoice, result)
        self._check_due_date(invoice, result)
        self._check_amount_due(invoice, result)
        self._check_items_sum(invoice, result)
        self._check_invoice_id(invoice, result)
        self._check_items_amounts(invoice, result)
        self._check_recommended_fields(invoice, result)
        self._check_currency(invoice, result)
        self._check_dit_confidence(invoice, result)

        # Update Invoice 
        invoice.is_valid            = result.is_valid
        invoice.validation_errors   = result.errors
        invoice.validation_warnings = result.warnings

        if result.is_valid:
            logger.info(
                f"Validation passed: {invoice.vendor_name}"
                + (f" ({len(result.warnings)} warning(s))"
                   if result.warnings else "")
            )
        else:
            logger.warning(
                f"Validation failed: {invoice.vendor_name} "
                f"→ {result.errors}"
            )

        return result
    # BLOCKING RULES 

    def _check_required_fields(self, invoice: Invoice, result: ValidationResult) -> None:
        """Only REQUIRED_FIELDS block validation."""
        for field, label in REQUIRED_FIELDS.items():
            if not getattr(invoice, field):
                result.add_error(
                    f"Required field missing: {label} ({field})"
                )

    def _check_date(self, invoice: Invoice, result: ValidationResult) -> None:
        """Check date format and validity."""
        d = invoice.invoice_date
        if not d:
            return

        if not DATE_PATTERN.match(str(d)):
            result.add_error(
                f"Invalid date format: '{d}'. Expected: YYYY-MM-DD"
            )
            return

        try:
            parsed = datetime.strptime(str(d), "%Y-%m-%d").date()
        except ValueError:
            result.add_error(f"Impossible date: '{d}'")
            return

        if parsed > date.today():
            result.add_warning(f"Future invoice date: '{d}'")

        if parsed.year < date.today().year - 20:
            result.add_warning(f"Invoice date too old (>20 years): '{d}'")

    # NON-BLOCKING RULES (warnings only) 

    def _check_recommended_fields(self, invoice: Invoice, result: ValidationResult) -> None:
        """Warn if recommended fields are missing."""
        for field, label in RECOMMENDED_FIELDS.items():
            if not getattr(invoice, field):
                result.add_warning(
                    f"Recommended field missing: {label} ({field})"
                )

    def _check_amounts(self, invoice: Invoice, result: ValidationResult) -> None:
        """Check amounts are positive (warning only)."""
        fields = {
            "total_amount":   "Total amount",
            "subtotal":       "Subtotal",
            "tax_amount":     "Tax amount",
            "total_discount": "Discount",
            "amount_due":     "Amount due",
        }
        for attr, label in fields.items():
            value = getattr(invoice, attr)
            if value is not None:
                try:
                    if float(value) < 0:
                        result.add_warning(f"Negative amount: {label} = {value}")
                except (TypeError, ValueError):
                    result.add_warning(f"Non-numeric amount: {label} = '{value}'")

    def _check_math(self, invoice: Invoice, result: ValidationResult) -> None:
        """
        Check mathematical consistency.
        Uses 2% tolerance for OCR errors. WARNING only.
        """
        subtotal = invoice.subtotal
        tax      = invoice.tax_amount
        total    = invoice.total_amount
        discount = invoice.total_discount or 0.0

        if any(v is None for v in [subtotal, total]):
            return

        try:
            actual = round(float(total), 2)
            tolerance = max(MATH_TOLERANCE, actual * OCR_MATH_TOLERANCE_PCT)

            # Case 1: Tax exclusive (subtotal + tax ≈ total)
            if tax is not None:
                computed = round(float(subtotal) - float(discount) + float(tax), 2)
                if abs(computed - actual) <= tolerance:
                    return 

                result.add_warning(
                    f"Math mismatch: Subtotal({subtotal}) - Discount({discount}) "
                    f"+ Tax({tax}) = {computed} ≠ Total({actual}). "
                    f"Diff: {abs(computed - actual):.2f} ({abs(computed - actual)/actual*100:.1f}%)"
                )
            else:
                # Case 2: Tax inclusive (subtotal ≈ total)
                if abs(float(subtotal) - actual) <= tolerance:
                    return  

                result.add_warning(
                    f"Subtotal ({subtotal}) ≠ Total ({total}). "
                    f"Diff: {abs(float(subtotal) - actual):.2f}"
                )

        except (TypeError, ValueError) as e:
            result.add_warning(f"Cannot verify math consistency: {e}")

    def _check_due_date(self, invoice: Invoice, result: ValidationResult) -> None:
        """Check due date is after invoice date (warning only)."""
        if not invoice.invoice_date or not invoice.due_date:
            return

        if not DATE_PATTERN.match(str(invoice.invoice_date)):
            return
        if not DATE_PATTERN.match(str(invoice.due_date)):
            result.add_warning(f"Invalid due date format: '{invoice.due_date}'")
            return

        try:
            invoice_dt = datetime.strptime(str(invoice.invoice_date), "%Y-%m-%d").date()
            due_dt = datetime.strptime(str(invoice.due_date), "%Y-%m-%d").date()

            if due_dt < invoice_dt:
                result.add_warning(
                    f"Due date ({invoice.due_date}) "
                    f"before invoice date ({invoice.invoice_date})"
                )
        except ValueError:
            result.add_warning(
                f"Cannot compare dates: "
                f"invoice_date='{invoice.invoice_date}', due_date='{invoice.due_date}'"
            )

    def _check_amount_due(self, invoice: Invoice, result: ValidationResult) -> None:
        """Check amount due does not exceed total (warning only)."""
        if invoice.amount_due is None or invoice.total_amount is None:
            return

        try:
            amount_due = float(invoice.amount_due)
            total_amount = float(invoice.total_amount)

            if amount_due > total_amount + MATH_TOLERANCE:
                result.add_warning(
                    f"Amount due ({invoice.amount_due}) "
                    f"exceeds total ({invoice.total_amount})"
                )
        except (TypeError, ValueError) as e:
            result.add_warning(f"Cannot verify amount due: {e}")

    def _check_items_sum(self, invoice: Invoice, result: ValidationResult) -> None:
        """
        Check items sum ≈ subtotal.
        Uses 5% tolerance for OCR errors on line items. WARNING only.
        """
        if not invoice.items or invoice.subtotal is None:
            return

        try:
            items_with_amount = [
                item for item in invoice.items
                if item.get("amount") is not None
            ]

            # If some items don't have amounts, we can't verify
            if len(items_with_amount) < len(invoice.items):
                return

            items_sum = round(sum(float(item["amount"]) for item in items_with_amount), 2)
            subtotal = round(float(invoice.subtotal), 2)
            tolerance = max(MATH_TOLERANCE, subtotal * OCR_MATH_TOLERANCE_PCT)

            if abs(items_sum - subtotal) <= tolerance:
                return  

            result.add_warning(
                f"Items sum ({items_sum}) ≈ Subtotal ({subtotal}). "
                f"Diff: {abs(items_sum - subtotal):.2f} "
                f"({abs(items_sum - subtotal)/subtotal*100:.1f}%)"
            )
        except (TypeError, ValueError) as e:
            result.add_warning(f"Cannot verify items sum: {e}")

    def _check_invoice_id(self, invoice: Invoice, result: ValidationResult) -> None:
        """Check invoice ID format (warning only)."""
        if invoice.invoice_id is None:
            return

        invoice_id = str(invoice.invoice_id).strip()

        if len(invoice_id) == 0:
            result.add_warning("Invoice ID is empty")
        elif len(invoice_id) < 2:
            result.add_warning(f"Suspicious Invoice ID (too short): '{invoice_id}'")

    def _check_items_amounts(self, invoice: Invoice, result: ValidationResult) -> None:
        """Check line items have positive amounts (warning only)."""
        if not invoice.items:
            return

        for idx, item in enumerate(invoice.items, start=1):
            amount = item.get("amount")
            if amount is None:
                continue

            try:
                if float(amount) < 0:
                    description = item.get("description", f"Item {idx}")
                    result.add_warning(
                        f"Negative amount line {idx} ('{description}'): {amount}"
                    )
            except (TypeError, ValueError):
                result.add_warning(f"Non-numeric amount line {idx}: '{amount}'")

    def _check_currency(self, invoice: Invoice, result: ValidationResult) -> None:
        """Warn if currency is unusual."""
        if not invoice.currency:
            return
        if invoice.currency.upper() not in VALID_CURRENCIES:
            result.add_warning(
                f"Unusual currency: '{invoice.currency}'. "
                f"Known currencies: {VALID_CURRENCIES}"
            )

    def _check_dit_confidence(self, invoice: Invoice, result: ValidationResult) -> None:
        """Warn only if DiT confidence is very low (< 0.3)."""
        if invoice.dit_confidence is None:
            return

        if invoice.dit_confidence < 0.3:
            result.add_warning(
                f"Low DiT confidence: {invoice.dit_confidence:.3f} "
                f"— manual review recommended"
            )