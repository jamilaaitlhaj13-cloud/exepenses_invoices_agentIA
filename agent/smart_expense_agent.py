# agent/smart_expense_agent.py

import logging
import time
from pathlib import Path

from config.settings import (
    CYCLE_INTERVAL_MINUTES,
    MAX_RETRY_ATTEMPTS,
)
from models.invoice              import Invoice
from tools.mail_fetcher_tool     import MailFetcherTool
from tools.document_verifier_tool import DocumentVerifierTool
from tools.ocr_extraction_tool   import OCRExtractionTool
from tools.ai_classifier_tool    import AIClassifierTool
from tools.validation_tool       import ValidationTool
from tools.export_tool           import ExportTool
from tools.dataset_builder_tool  import DatasetBuilderTool

logger = logging.getLogger(__name__)


class SmartExpenseAgent:
    """
    Orchestrates the complete invoice processing pipeline:

    1. MailFetcherTool      → LLM filter on email metadata
    2. DocumentVerifierTool → DiT visual classification (98% accuracy)
    3. OCRExtractionTool    → Azure Document Intelligence extraction
    4. AIClassifierTool     → LLM classification + reformatting
    5. ValidationTool       → Business rules (12 rules)
    6. DatasetBuilderTool   → Storage for future fine-tuning
    7. ExportTool           → Excel report per category
    """

    def __init__(self):
        self.mail_fetcher    = MailFetcherTool()
        self.doc_verifier    = DocumentVerifierTool()
        self.ocr             = OCRExtractionTool()
        self.classifier      = AIClassifierTool()
        self.validator       = ValidationTool()
        self.exporter        = ExportTool()
        self.dataset_builder = DatasetBuilderTool()

    def run(self) -> None:
        logger.info("=" * 60)
        logger.info("SmartExpenseAgent started")
        logger.info(f"Cycle interval: {CYCLE_INTERVAL_MINUTES} min")
        logger.info("=" * 60)

        while True:
            try:
                self.run_cycle()
            except KeyboardInterrupt:
                logger.info("Agent stopped by user")
                break
            except Exception as e:
                logger.error(f"Unexpected error: {e}", exc_info=True)

            logger.info(
                f"Waiting {CYCLE_INTERVAL_MINUTES} min before next cycle..."
            )
            time.sleep(CYCLE_INTERVAL_MINUTES * 60)

    def run_cycle(self) -> dict:
        logger.info("-" * 60)
        logger.info("New cycle started")

        # ── Step 1: Email collection ───────────────────
        files: list[Path] = self.mail_fetcher.fetch_invoices()

        if not files:
            logger.info("No documents to process — cycle complete")
            return {"total": 0, "validated": 0, "failed": 0, "exported": []}

        logger.info(f"{len(files)} document(s) collected")

        # ── Step 2: Process each file ──────────────────
        validated: list[Invoice] = []
        failed = 0

        for file_path in files:
            invoice = self._process(file_path)
            if invoice:
                validated.append(invoice)
            else:
                failed += 1

        # ── Step 3: Batch export ───────────────────────
        exported_files = []
        if validated:
            dataset_stats = self.dataset_builder.add_batch(validated)
            logger.info(
                f"Dataset updated: "
                f"{dataset_stats['added']} added, "
                f"{dataset_stats['skipped']} skipped"
            )

            exported = self.exporter.export(validated)
            exported_files = [str(p) for p in exported]

            for invoice in validated:
                if invoice.source_file:
                    self.exporter.move_to_valid_invoices(invoice.source_file)
                    self.exporter.cleanup_pending(invoice.source_file)
                    self.mail_fetcher.mark_as_validated(invoice.source_file)

        # ── Cycle summary ──────────────────────────────
        summary = {
            "total":     len(files),
            "validated": len(validated),
            "failed":    failed,
            "exported":  exported_files,
        }

        logger.info("-" * 60)
        logger.info(
            f"Cycle complete: "
            f"{summary['validated']}/{summary['total']} valid | "
            f"{summary['failed']} failed | "
            f"{len(exported_files)} Excel file(s)"
        )

        return summary

    def _process(self, file_path: Path) -> Invoice | None:
        """
        Process an invoice file end-to-end.

        Steps:
        1. DiT verification (once, before retry)
        2. OCR → Classification → Validation (with retry)
        3. Notification on definitive failure
        """
        logger.info(f"Processing: {file_path.name}")

        invoice = Invoice(source_file=file_path)
        invoice.attempt_count = 0
        last_errors = []

        # ── DiT visual verification BEFORE retry ──────
        # The document doesn't change → verify only once
        try:
            is_invoice, dit_score, confidence = self.doc_verifier.verify(file_path)
            invoice.dit_confidence = dit_score
            invoice.dit_label = "INVOICE" if is_invoice else "NON_INVOICE"
            invoice.dit_is_invoice = is_invoice

            if not is_invoice:
                logger.warning(
                    f"DiT rejected: {file_path.name} "
                    f"(score={dit_score:.3f}, confidence={confidence})"
                )
                self.exporter.move_to_need_review(file_path)
                self.mail_fetcher.mark_as_rejected(file_path)
                return None

            logger.info(
                f"DiT confirmed invoice: {file_path.name} "
                f"(score={dit_score:.3f}, confidence={confidence})"
            )

        except Exception as e:
            logger.error(f"DocumentVerifier error: {e}")
            self.exporter.move_to_need_review(file_path)
            return None

        # ── Retry on OCR + Classification + Validation ──
        for attempt in range(1, MAX_RETRY_ATTEMPTS + 1):
            invoice.attempt_count = attempt

            try:
                logger.info(
                    f"  Attempt {attempt}/{MAX_RETRY_ATTEMPTS}: {file_path.name}"
                )

                self.ocr.extract(invoice)
                self.classifier.classify(invoice)
                result = self.validator.validate(invoice)

                if not result.is_valid:
                    last_errors = result.errors
                    raise ValueError(f"Validation failed: {result.errors}")

                logger.info(
                    f"  Success ({attempt}/{MAX_RETRY_ATTEMPTS}): "
                    f"{invoice.vendor_name} → "
                    f"{invoice.expense_category} | "
                    f"LLM: {invoice.llm_confidence}"
                )

                return invoice

            except ValueError as e:
                last_errors = [str(e)]
                logger.warning(
                    f"  Attempt {attempt}/{MAX_RETRY_ATTEMPTS} ValueError: {e}"
                )
                if attempt < MAX_RETRY_ATTEMPTS:
                    invoice = Invoice(source_file=file_path)
                    invoice.dit_confidence = dit_score
                    invoice.dit_label = "INVOICE" if is_invoice else "NON_INVOICE"
                    invoice.dit_is_invoice = is_invoice
                    invoice.attempt_count = attempt

            except RuntimeError as e:
                last_errors = [str(e)]
                logger.error(
                    f"  Attempt {attempt}/{MAX_RETRY_ATTEMPTS} RuntimeError: {e}"
                )
                if attempt < MAX_RETRY_ATTEMPTS:
                    invoice = Invoice(source_file=file_path)
                    invoice.dit_confidence = dit_score
                    invoice.dit_label = "INVOICE" if is_invoice else "NON_INVOICE"
                    invoice.dit_is_invoice = is_invoice
                    invoice.attempt_count = attempt

            if attempt < MAX_RETRY_ATTEMPTS:
                wait = 2 ** attempt
                logger.info(f"  Retry in {wait}s...")
                time.sleep(wait)

        # ── Definitive failure ─────────────────────────
        logger.error(
            f"Definitive failure after {MAX_RETRY_ATTEMPTS} attempts: {file_path.name}"
        )

        self.exporter.move_to_need_review(file_path)
        self.mail_fetcher.notify_accountant(
            filename=file_path.name,
            errors=last_errors or ["Unknown error"],
        )

        return None