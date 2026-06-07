# tests/test_validation_tool.py
"""
Unit tests for ValidationTool, AIClassifierTool._is_valid_date,
and DatasetBuilderTool._is_duplicate / _make_key.

Run: pytest tests/ -v
"""

import json
import tempfile
import pytest
from pathlib import Path
from datetime import datetime

# ── Helpers ────────────────────────────────────────────────────────────────────

def make_invoice(**kwargs):
    """Create a minimal valid Invoice for testing."""
    from models.invoice import Invoice
    inv = Invoice(
        vendor_name="Test Vendor",
        invoice_date="2024-06-01",
        total_amount=1000.0,
        currency="EUR",
    )
    for k, v in kwargs.items():
        setattr(inv, k, v)
    return inv


# ══════════════════════════════════════════════════════════════════════════════
# ValidationTool
# ══════════════════════════════════════════════════════════════════════════════

class TestValidationTool:

    @pytest.fixture(autouse=True)
    def setup(self):
        from tools.validation_tool import ValidationTool
        self.tool = ValidationTool()

    # ── Required fields ────────────────────────────────────────────────────

    def test_valid_invoice_passes(self):
        inv    = make_invoice()
        result = self.tool.validate(inv)
        assert result.is_valid
        assert result.errors == []

    def test_missing_vendor_name_blocks(self):
        inv    = make_invoice(vendor_name=None)
        result = self.tool.validate(inv)
        assert not result.is_valid
        assert any("vendor_name" in e for e in result.errors)

    def test_missing_invoice_date_blocks(self):
        inv    = make_invoice(invoice_date=None)
        result = self.tool.validate(inv)
        assert not result.is_valid
        assert any("invoice_date" in e for e in result.errors)

    def test_missing_total_amount_blocks(self):
        inv    = make_invoice(total_amount=None)
        result = self.tool.validate(inv)
        assert not result.is_valid
        assert any("total_amount" in e for e in result.errors)

    # ── Date format ────────────────────────────────────────────────────────

    def test_wrong_date_format_blocks(self):
        inv    = make_invoice(invoice_date="01/06/2024")
        result = self.tool.validate(inv)
        assert not result.is_valid
        assert any("YYYY-MM-DD" in e for e in result.errors)

    def test_future_date_warns_not_blocks(self):
        inv    = make_invoice(invoice_date="2099-01-01")
        result = self.tool.validate(inv)
        assert result.is_valid               # not a blocking error
        assert any("Future" in w for w in result.warnings)

    def test_old_date_warns_not_blocks(self):
        inv    = make_invoice(invoice_date="2001-01-01")
        result = self.tool.validate(inv)
        # 2001 is > 20 years ago from 2026
        assert any("old" in w.lower() for w in result.warnings)

    # ── Math consistency ───────────────────────────────────────────────────

    def test_math_consistent_passes(self):
        inv = make_invoice(subtotal=800.0, tax_amount=200.0, total_amount=1000.0)
        result = self.tool.validate(inv)
        assert not any("Math mismatch" in w for w in result.warnings)

    def test_math_mismatch_warns_not_blocks(self):
        inv    = make_invoice(subtotal=500.0, tax_amount=200.0, total_amount=1000.0)
        result = self.tool.validate(inv)
        assert result.is_valid
        assert any("Math mismatch" in w or "mismatch" in w.lower() for w in result.warnings)

    def test_math_tolerance_accepted(self):
        """A difference within 2% tolerance should not produce a warning."""
        inv    = make_invoice(subtotal=800.0, tax_amount=199.5, total_amount=1000.0)
        result = self.tool.validate(inv)
        assert not any("mismatch" in w.lower() for w in result.warnings)

    # ── Currency ───────────────────────────────────────────────────────────

    def test_known_currency_no_warning(self):
        for currency in ("MAD", "EUR", "USD", "GBP", "CHF", "AED"):
            inv    = make_invoice(currency=currency)
            result = self.tool.validate(inv)
            assert not any("Unusual currency" in w for w in result.warnings), \
                f"{currency} should be valid"

    def test_unknown_currency_warns(self):
        inv    = make_invoice(currency="XYZ")
        result = self.tool.validate(inv)
        assert any("Unusual currency" in w for w in result.warnings)

    # ── Due date ───────────────────────────────────────────────────────────

    def test_due_date_before_invoice_date_warns(self):
        inv    = make_invoice(invoice_date="2024-06-01", due_date="2024-05-01")
        result = self.tool.validate(inv)
        assert any("Due date" in w and "before" in w for w in result.warnings)

    def test_due_date_after_invoice_date_ok(self):
        inv    = make_invoice(invoice_date="2024-06-01", due_date="2024-07-01")
        result = self.tool.validate(inv)
        assert not any("before" in w for w in result.warnings)

    # ── DiT confidence ────────────────────────────────────────────────────

    def test_low_dit_confidence_warns(self):
        inv    = make_invoice(dit_confidence=0.2)
        result = self.tool.validate(inv)
        assert any("DiT" in w for w in result.warnings)

    def test_high_dit_confidence_no_warning(self):
        inv    = make_invoice(dit_confidence=0.95)
        result = self.tool.validate(inv)
        assert not any("DiT" in w for w in result.warnings)

    # ── Negative amounts ──────────────────────────────────────────────────

    def test_negative_total_warns_not_blocks(self):
        inv    = make_invoice(total_amount=-100.0)
        result = self.tool.validate(inv)
        assert result.is_valid
        assert any("Negative" in w for w in result.warnings)

    # ── Invoice ID ────────────────────────────────────────────────────────

    def test_short_invoice_id_warns(self):
        inv    = make_invoice(invoice_id="A")
        result = self.tool.validate(inv)
        assert any("short" in w.lower() for w in result.warnings)


# ══════════════════════════════════════════════════════════════════════════════
# AIClassifierTool._is_valid_date
# ══════════════════════════════════════════════════════════════════════════════

class TestIsValidDate:
    """Test the date validation helper without instantiating the full LLM client."""

    @pytest.fixture(autouse=True)
    def setup(self):
        # We test the method directly without initializing AzureChatOpenAI
        from tools.ai_classifier_tool import AIClassifierTool
        # Create instance bypassing __init__ to avoid needing Azure credentials
        self.obj = object.__new__(AIClassifierTool)

    def test_valid_date(self):
        assert self.obj._is_valid_date("2024-06-01") is True

    def test_wrong_format(self):
        assert self.obj._is_valid_date("01/06/2024") is False
        assert self.obj._is_valid_date("2024/06/01") is False
        assert self.obj._is_valid_date("June 1 2024") is False

    def test_year_below_2000(self):
        assert self.obj._is_valid_date("1999-12-31") is False

    def test_year_at_current_plus_5(self):
        max_year = datetime.now().year + 5
        assert self.obj._is_valid_date(f"{max_year}-01-01") is True

    def test_year_above_limit(self):
        max_year = datetime.now().year + 6
        assert self.obj._is_valid_date(f"{max_year}-01-01") is False

    def test_empty_string(self):
        assert self.obj._is_valid_date("") is False

    def test_none(self):
        assert self.obj._is_valid_date(None) is False

    def test_impossible_date(self):
        assert self.obj._is_valid_date("2024-13-01") is False  # month 13
        assert self.obj._is_valid_date("2024-02-30") is False  # Feb 30


# ══════════════════════════════════════════════════════════════════════════════
# DatasetBuilderTool — in-memory duplicate detection
# ══════════════════════════════════════════════════════════════════════════════

class TestDatasetBuilderDuplicates:

    @pytest.fixture
    def tmp_builder(self, tmp_path):
        """Create a DatasetBuilderTool pointing to a temp directory."""
        from tools.dataset_builder_tool import DatasetBuilderTool
        return DatasetBuilderTool(output_dir=str(tmp_path))

    @pytest.fixture
    def builder_with_data(self, tmp_path):
        """
        DatasetBuilderTool pre-seeded with one JSONL entry.
        """
        jsonl_path = tmp_path / "invoices_dataset.jsonl"
        entry = {
            "invoice_id": "INV-001",
            "vendor":     "Test Corp",
            "label":      "SaaS",
        }
        jsonl_path.write_text(json.dumps(entry) + "\n", encoding="utf-8")

        from tools.dataset_builder_tool import DatasetBuilderTool
        return DatasetBuilderTool(output_dir=str(tmp_path))

    def test_empty_dataset_no_duplicate(self, tmp_builder):
        assert tmp_builder._is_duplicate("INV-999", "Some Vendor") is False

    def test_none_invoice_id_never_duplicate(self, tmp_builder):
        assert tmp_builder._is_duplicate(None, "Any Vendor") is False

    def test_existing_entry_detected_as_duplicate(self, builder_with_data):
        assert builder_with_data._is_duplicate("INV-001", "Test Corp") is True

    def test_different_vendor_not_duplicate(self, builder_with_data):
        assert builder_with_data._is_duplicate("INV-001", "Other Corp") is False

    def test_case_insensitive(self, builder_with_data):
        assert builder_with_data._is_duplicate("inv-001", "test corp") is True

    def test_make_key_normalizes(self):
        from tools.dataset_builder_tool import DatasetBuilderTool
        assert DatasetBuilderTool._make_key("  INV-001  ", "  Test Corp  ") == (
            "inv-001", "test corp"
        )

    def test_index_updated_after_add(self, tmp_builder):
        """After adding an invoice, subsequent _is_duplicate checks return True."""
        inv = make_invoice(
            invoice_id="INV-NEW",
            vendor_name="New Vendor",
            expense_category="SaaS",
            llm_confidence="high",
        )
        from tools.validation_tool import ValidationTool
        ValidationTool().validate(inv)   # sets inv.is_valid = True

        tmp_builder.add_invoice(inv)

        # Should now be detected as duplicate
        assert tmp_builder._is_duplicate("INV-NEW", "New Vendor") is True


# ══════════════════════════════════════════════════════════════════════════════
# ExportTool — thread safety smoke test
# ══════════════════════════════════════════════════════════════════════════════

class TestExportToolLocking:
    """
    FIX: import from tools._locks (no pandas) instead of tools.export_tool
         to avoid the NumPy 1.x/2.x incompatibility error on Anaconda envs.
    """

    def test_get_file_lock_same_path_same_object(self, tmp_path):
        from tools._locks import _get_file_lock
        p     = tmp_path / "test.xlsx"
        lock1 = _get_file_lock(p)
        lock2 = _get_file_lock(p)
        assert lock1 is lock2, "Same path must return the same Lock instance"

    def test_get_file_lock_different_paths_different_objects(self, tmp_path):
        from tools._locks import _get_file_lock
        lock1 = _get_file_lock(tmp_path / "a.xlsx")
        lock2 = _get_file_lock(tmp_path / "b.xlsx")
        assert lock1 is not lock2


# ══════════════════════════════════════════════════════════════════════════════
# Password security
# ══════════════════════════════════════════════════════════════════════════════

class TestPasswordSecurity:
    """
    Ensure bcrypt is used — not plain SHA-256.
    FIX: import from utils.auth (no pandas) instead of app.py
         to avoid the NumPy 1.x/2.x incompatibility error on Anaconda envs.
    """

    def test_hash_is_bcrypt(self):
        from utils.auth import hash_password
        hashed = hash_password("TestPassword123")
        assert hashed.startswith("$2b$"), "Hash must be a bcrypt hash"

    def test_check_password_correct(self):
        from utils.auth import hash_password, check_password
        hashed = hash_password("MySecret!")
        assert check_password("MySecret!", hashed) is True

    def test_check_password_wrong(self):
        from utils.auth import hash_password, check_password
        hashed = hash_password("MySecret!")
        assert check_password("WrongPassword", hashed) is False

    def test_upgrade_legacy_hash_accepts_sha256(self):
        """Legacy SHA-256 password should be accepted and upgraded to bcrypt."""
        import hashlib
        from utils.auth import upgrade_legacy_hash
        legacy = hashlib.sha256("OldPassword".encode()).hexdigest()
        is_valid, new_hash = upgrade_legacy_hash("OldPassword", legacy)
        assert is_valid is True
        assert new_hash is not None
        assert new_hash.startswith("$2b$")

    def test_upgrade_legacy_hash_rejects_wrong(self):
        import hashlib
        from utils.auth import upgrade_legacy_hash
        legacy = hashlib.sha256("OldPassword".encode()).hexdigest()
        is_valid, new_hash = upgrade_legacy_hash("WrongPassword", legacy)
        assert is_valid is False
        assert new_hash is None