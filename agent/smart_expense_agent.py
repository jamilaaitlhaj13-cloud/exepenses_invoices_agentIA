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
from tools.image_enhancer_tool   import ImageEnhancerTool

logger = logging.getLogger(__name__)


class SmartExpenseAgent:
    """
    Orchestrates the complete invoice processing pipeline:

    1. MailFetcherTool      → LLM filter on email metadata
    2. DocumentVerifierTool → DiT visual classification (99.5% accuracy)
    3. ImageEnhancerTool    → Progressive image enhancement for OCR retry
    4. OCRExtractionTool    → Azure Document Intelligence extraction
    5. AIClassifierTool     → LLM classification + reformatting
    6. ValidationTool       → Business rules (12 rules)
    7. DatasetBuilderTool   → Storage for future fine-tuning
    8. ExportTool           → Excel report per category
    """

    def __init__(self, company_id: int | None = None, auth_callback=None):
        from pathlib import Path as _Path
        _root = _Path(__file__).resolve().parent.parent
        _name = f"ms_token_{company_id}.json" if company_id else "ms_token.json"
        token_file = str(_root / _name)
        self.mail_fetcher    = MailFetcherTool(token_file=token_file, auth_callback=auth_callback)
        self.doc_verifier    = DocumentVerifierTool()
        self.enhancer        = ImageEnhancerTool()
        self.ocr             = OCRExtractionTool()
        self.classifier      = AIClassifierTool()
        self.validator       = ValidationTool()
        self.exporter        = ExportTool()
        self.dataset_builder = DatasetBuilderTool()

    # MAIN LOOP

    def run(self) -> None:
        """Run the agent in continuous mode (production)."""
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

    # CYCLE

    def run_cycle(self) -> dict:
        """Run a single processing cycle."""
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
        rejected:  list[Invoice] = []
        failed = 0

        for file_path in files:
            invoice = self._process(file_path)
            if invoice and invoice.dit_is_invoice:
                validated.append(invoice)
            elif invoice and not invoice.dit_is_invoice:
                # High-confidence DiT rejection — logged to DB by the caller
                rejected.append(invoice)
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
            "rejected":  len(rejected),
            "rejected_invoices": rejected,
            "failed":    failed,
            "exported":  exported_files,
        }

        logger.info("-" * 60)
        logger.info(
            f"Cycle complete: "
            f"{summary['validated']}/{summary['total']} valid | "
            f"{summary['rejected']} rejected by DiT | "
            f"{summary['failed']} failed | "
            f"{len(exported_files)} Excel file(s)"
        )

        return summary

    # SINGLE FILE PROCESSING

    def _process(self, file_path: Path) -> Invoice | None:
        """
        Process an invoice file end-to-end.

        Steps:
        1. DiT visual verification (once, before retry)
        2. OCR with progressive image enhancement (with retry)
        3. LLM Classification
        4. Validation
        5. Notification on definitive failure
        """
        logger.info(f"Processing: {file_path.name}")

        invoice = Invoice(source_file=file_path)
        invoice.attempt_count = 0
        last_errors = []

        # STEP 1: DiT visual verification (ONCE)
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
                invoice.source_filename = file_path.name

        except Exception as e:
            logger.error(f"DocumentVerifier error: {e}")
            self.exporter.move_to_need_review(file_path)
            return None

        if not invoice.dit_is_invoice:
            try:
                self.mail_fetcher.mark_as_rejected(file_path)
            except Exception:
                pass  # upload context: no email to mark as read
            return invoice

        logger.info(
            f"DiT confirmed invoice: {file_path.name} "
            f"(score={dit_score:.3f}, confidence={confidence})"
        )

        # STEP 2: OCR + Classification + Validation (with intelligent retry)

        # Pre-load the image ONCE for all retry attempts
        base_image = self.enhancer.load_image(file_path)

        for attempt in range(1, MAX_RETRY_ATTEMPTS + 1):
            invoice.attempt_count = attempt

            # Get the appropriate image for this attempt
            enhanced_path, was_enhanced = self.enhancer.enhance_for_attempt(
                file_path, attempt, base_image=base_image
            )

            try:
                logger.info(
                    f"  Attempt {attempt}/{MAX_RETRY_ATTEMPTS}: {file_path.name}"
                )

                # Update source file to enhanced version
                invoice.source_file = enhanced_path

                # ── OCR 
                self.ocr.extract(invoice)

                # ── Classification 
                self.classifier.classify(invoice)

                # ── Validation 
                result = self.validator.validate(invoice)

                if not result.is_valid:
                    last_errors = result.errors
                    raise ValueError(f"Validation failed: {result.errors}")

                # ── SUCCESS 
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

            except RuntimeError as e:
                last_errors = [str(e)]
                logger.error(
                    f"  Attempt {attempt}/{MAX_RETRY_ATTEMPTS} RuntimeError: {e}"
                )

            finally:
                # Clean up enhanced temp file
                if was_enhanced:
                    self.enhancer.cleanup(enhanced_path)

            # ── Prepare for next attempt 
            if attempt < MAX_RETRY_ATTEMPTS:
                # Reset invoice but keep DiT scores and source_file
                invoice = Invoice(source_file=file_path)
                invoice.dit_confidence = dit_score
                invoice.dit_label = "INVOICE" if is_invoice else "NON_INVOICE"
                invoice.dit_is_invoice = is_invoice
                invoice.attempt_count = attempt

                # Exponential backoff
                wait = 2 ** attempt
                logger.info(f"  Retry in {wait}s with enhanced image...")
                time.sleep(wait)

        
        # DEFINITIVE FAILURE
        
        logger.error(
            f"Definitive failure after {MAX_RETRY_ATTEMPTS} attempts: {file_path.name}"
        )

        self.exporter.move_to_need_review(file_path)
        try:
            self.mail_fetcher.notify_accountant(
                filename=file_path.name,
                errors=last_errors or ["Unknown error"],
            )
        except Exception:
            pass  

        return None