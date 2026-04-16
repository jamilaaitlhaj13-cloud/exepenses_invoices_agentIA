import logging
import re
from datetime import datetime, date

from models.invoice import Invoice
from models.validation_result import ValidationResult

logger = logging.getLogger(__name__)

# Tolerance for accounting rounding (2 cents)
MATH_TOLERANCE = 0.02

# ISO date pattern: YYYY-MM-DD
DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class ValidationTool:

    def validate(self, invoice: Invoice) -> ValidationResult:
        """
        Validates the consistency of an invoice's data.

        Args:
            invoice: Invoice object after LLM classification

        Returns:
            ValidationResult(is_valid=True)  if all rules pass
            ValidationResult(is_valid=False, errors=[...]) otherwise
        """
        result = ValidationResult(is_valid=True)

        # Apply the 4 business rules
        self._check_required_fields(invoice, result)
        self._check_date(invoice, result)
        self._check_amounts(invoice, result)
        self._check_math(invoice, result)

        # Update the Invoice object with validation result
        invoice.is_valid          = result.is_valid
        invoice.validation_errors = result.errors

        if result.is_valid:
            logger.info(f"Validation passed: {invoice.vendor_name}")
        else:
            logger.warning(
                f"Validation failed: {invoice.vendor_name} "
                f"-> {result.errors}"
            )

        return result

    # ── Rule 1: required fields ────────────────────────────

    def _check_required_fields(self, invoice: Invoice,
                                result: ValidationResult) -> None:
        """Checks that all mandatory fields are present."""
        required = {
            "vendor_name":  "Vendor name",
            "invoice_date": "Invoice date",
            "total_amount": "Total amount",
        }
        for field, label in required.items():
            if not getattr(invoice, field):
                result.add_error(
                    f"Missing required field: {label} ({field})"
                )

    # ── Rule 2: date format ────────────────────────────────

    def _check_date(self, invoice: Invoice,
                    result: ValidationResult) -> None:
        """Checks that the invoice date is valid and in YYYY-MM-DD format."""
        d = invoice.invoice_date
        if not d:
            return  # Already reported by _check_required_fields

        # Check YYYY-MM-DD format
        if not DATE_PATTERN.match(str(d)):
            result.add_error(
                f"Invalid date format: '{d}'. "
                f"Expected format: YYYY-MM-DD"
            )
            return

        # Check that the date is a valid calendar date
        try:
            parsed = datetime.strptime(str(d), "%Y-%m-%d").date()
        except ValueError:
            result.add_error(f"Impossible date: '{d}'")
            return

        # Invoice date cannot be in the future
        if parsed > date.today():
            result.add_error(f"Invoice date is in the future: '{d}'")

        # Invoice older than 5 years is suspicious
        if parsed.year < date.today().year - 5:
            result.add_error(
                f"Invoice date is too old (> 5 years): '{d}'"
            )

    # ── Rule 3: positive amounts ───────────────────────────

    def _check_amounts(self, invoice: Invoice,
                       result: ValidationResult) -> None:
        """Checks that all monetary amounts are positive."""
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
                        result.add_error(
                            f"Negative amount: {label} = {value}"
                        )
                except (TypeError, ValueError):
                    result.add_error(
                        f"Non-numeric amount: {label} = '{value}'"
                    )

    # ── Rule 4: mathematical consistency ──────────────────

    def _check_math(self, invoice: Invoice,
                    result: ValidationResult) -> None:
        """
        Verifies: subtotal - discount + tax ≈ total
        Only checked if all three values are available.
        """
        subtotal = invoice.subtotal
        tax      = invoice.tax_amount
        total    = invoice.total_amount
        discount = invoice.total_discount or 0.0

        # Cannot verify if any value is missing
        if any(v is None for v in [subtotal, tax, total]):
            return

        try:
            computed = round(float(subtotal) - float(discount) + float(tax), 2)
            actual   = round(float(total), 2)

            if abs(computed - actual) > MATH_TOLERANCE:
                result.add_error(
                    f"Mathematical inconsistency: "
                    f"Subtotal({subtotal}) - Discount({discount}) + Tax({tax}) "
                    f"= {computed} != Total({actual}). "
                    f"Difference: {abs(computed - actual):.2f}"
                )
        except (TypeError, ValueError) as e:
            result.add_error(
                f"Cannot verify mathematical consistency: {e}"
            )