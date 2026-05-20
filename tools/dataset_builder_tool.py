# tools/dataset_builder_tool.py

"""
DatasetBuilderTool
──────────────────
Builds a training dataset automatically
from invoices VALIDATED by ValidationTool.

Prerequisite: invoice.is_valid must be True
              (set by ValidationTool)

Outputs:
  - invoices_dataset.csv   → for Excel analysis
  - invoices_dataset.jsonl → for HuggingFace fine-tuning
"""

import csv
import json
import logging
from datetime import datetime
from pathlib import Path

from models.invoice import Invoice

logger = logging.getLogger(__name__)

CSV_FIELDS = [
    "text", "label", "vendor", "invoice_id",
    "invoice_date", "amount", "currency",
    "llm_confidence", "dit_confidence",
    "validation_warnings", "source_file", "timestamp"
]

ACCEPTED_CONFIDENCES = {"high", "medium"}


class DatasetBuilderTool:
    """
    Collects validated invoices and stores them in a dataset
    for future fine-tuning.

    Must be called ONLY AFTER ValidationTool.
    Uses invoice.is_valid as main criterion.
    """

    def __init__(
        self,
        output_dir:     str = "data/dataset",
        csv_filename:   str = "invoices_dataset.csv",
        jsonl_filename: str = "invoices_dataset.jsonl"
    ):
        self.output_dir  = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.csv_path   = self.output_dir / csv_filename
        self.jsonl_path = self.output_dir / jsonl_filename

        if not self.csv_path.exists():
            with open(self.csv_path, "w", newline="",
                      encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
                writer.writeheader()

        logger.info(f"DatasetBuilder initialized → {self.output_dir}")

    def add_invoice(self, invoice: Invoice) -> bool:
        """
        Add a validated invoice to the training dataset.
        """
        if invoice.is_valid is None:
            logger.warning(
                f"ValidationTool not called for: "
                f"{invoice.vendor_name} — ignored"
            )
            return False

        if not invoice.is_valid:
            logger.debug(
                f"Invalid invoice ignored: {invoice.vendor_name} "
                f"→ {invoice.validation_errors}"
            )
            return False

        if not invoice.expense_category:
            logger.debug(
                f"Ignored — missing category: {invoice.vendor_name}"
            )
            return False

        if invoice.llm_confidence not in ACCEPTED_CONFIDENCES:
            logger.debug(
                f"Ignored — LLM confidence '{invoice.llm_confidence}' "
                f"insufficient: {invoice.vendor_name}"
            )
            return False

        if self._is_duplicate(invoice.invoice_id, invoice.vendor_name):
            logger.debug(
                f"Duplicate ignored: {invoice.invoice_id} "
                f"- {invoice.vendor_name}"
            )
            return False

        text   = self._build_text(invoice)
        sample = {
            "text":               text,
            "label":              invoice.expense_category,
            "vendor":             invoice.vendor_name,
            "invoice_id":         invoice.invoice_id,
            "invoice_date":       invoice.invoice_date,
            "amount":             invoice.total_amount,
            "currency":           invoice.currency,
            "llm_confidence":     invoice.llm_confidence,
            "dit_confidence":     round(invoice.dit_confidence, 3)
                                  if invoice.dit_confidence else None,
            "validation_warnings": invoice.validation_warnings
                                   if hasattr(invoice, "validation_warnings")
                                   else [],
            "source_file":        invoice.source_file.name
                                  if invoice.source_file else None,
            "timestamp":          datetime.now().isoformat()
        }

        self._write_csv(sample)
        self._write_jsonl(sample)

        logger.info(
            f"Sample added → {invoice.expense_category} "
            f"| {invoice.vendor_name} "
            f"| {invoice.total_amount} {invoice.currency} "
            f"| LLM: {invoice.llm_confidence}"
        )
        return True

    def add_batch(self, invoices: list[Invoice]) -> dict:
        """Add a list of validated invoices to the dataset."""
        added   = 0
        skipped = 0
        reasons = {
            "invalid":          0,
            "low_confidence":   0,
            "duplicate":        0,
            "missing_category": 0,
        }

        for invoice in invoices:
            if not invoice.is_valid:
                reasons["invalid"] += 1
                skipped += 1
            elif invoice.llm_confidence not in ACCEPTED_CONFIDENCES:
                reasons["low_confidence"] += 1
                skipped += 1
            elif not invoice.expense_category:
                reasons["missing_category"] += 1
                skipped += 1
            elif self._is_duplicate(invoice.invoice_id, invoice.vendor_name):
                reasons["duplicate"] += 1
                skipped += 1
            else:
                if self.add_invoice(invoice):
                    added += 1
                else:
                    skipped += 1

        logger.info(
            f"Batch complete — {added} added, {skipped} skipped "
            f"| Reasons: {reasons}"
        )
        return {"added": added, "skipped": skipped, "reasons": reasons}

    def _build_text(self, invoice: Invoice) -> str:
        """Convert structured invoice to ML text."""
        items = " | ".join(
            item.get("description", "")
            for item in (invoice.items or [])
            if item.get("description")
        ) or "N/A"

        return (
            f"vendor: {invoice.vendor_name or 'unknown'} [SEP] "
            f"invoice_id: {invoice.invoice_id or 'N/A'} [SEP] "
            f"date: {invoice.invoice_date or 'N/A'} [SEP] "
            f"total: {invoice.total_amount or 'N/A'} "
            f"{invoice.currency or ''} [SEP] "
            f"tax: {invoice.tax_amount or 'N/A'} [SEP] "
            f"items: {items}"
        ).strip()

    def _is_duplicate(self, invoice_id: str, vendor: str) -> bool:
        """Check if invoice already exists in JSONL."""
        if not invoice_id or not self.jsonl_path.exists():
            return False

        inv_id_clean = str(invoice_id).strip().lower()
        vendor_clean = str(vendor or "").strip().lower()

        try:
            with open(self.jsonl_path, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        data = json.loads(line)
                        if (
                            str(data.get("invoice_id", "")).strip().lower()
                            == inv_id_clean
                            and
                            str(data.get("vendor", "")).strip().lower()
                            == vendor_clean
                        ):
                            return True
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            logger.warning(f"Error reading JSONL: {e}")

        return False

    def _write_csv(self, sample: dict) -> None:
        with open(self.csv_path, "a", newline="",
                  encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
            writer.writerow({
                k: (json.dumps(v) if isinstance(v, list) else v)
                for k, v in sample.items()
            })

    def _write_jsonl(self, sample: dict) -> None:
        with open(self.jsonl_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(sample, ensure_ascii=False) + "\n")

    def get_stats(self) -> dict:
        """Return current dataset statistics."""
        if not self.jsonl_path.exists():
            return {
                "total":              0,
                "by_category":        {},
                "by_confidence":      {},
                "ready_for_training": False,
                "message":            "Dataset empty"
            }

        total        = 0
        by_category  = {}
        by_confidence = {}

        try:
            with open(self.jsonl_path, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        data  = json.loads(line)
                        label = data.get("label", "Other")
                        conf  = data.get("llm_confidence", "unknown")
                        total += 1
                        by_category[label]  = by_category.get(label, 0) + 1
                        by_confidence[conf] = by_confidence.get(conf, 0) + 1
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            logger.error(f"Error reading stats: {e}")
            return {"total": 0, "by_category": {}, "ready_for_training": False}

        ready   = total >= 200 and len(by_category) >= 3
        message = (
            "Ready for fine-tuning!"
            if ready else
            f"{max(0, 200 - total)} examples missing (minimum 200 required)"
        )

        return {
            "total":              total,
            "by_category":        by_category,
            "by_confidence":      by_confidence,
            "ready_for_training": ready,
            "training_threshold": 200,
            "message":            message,
        }