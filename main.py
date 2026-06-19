
import argparse
import logging
import sys
from pathlib import Path

# ── Logging configuration ──────────────────────────────────
file_handler = logging.FileHandler("app.log", encoding="utf-8")
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(logging.Formatter(
    "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
))

# Console handler: only WARNING and ERROR
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.WARNING)
console_handler.setFormatter(logging.Formatter(
    "%(levelname)-8s | %(message)s"
))

# Root logger configuration
logging.basicConfig(
    level=logging.DEBUG,
    handlers=[file_handler, console_handler]
)

# Reduce noise from external libraries
logging.getLogger("azure").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("openai").setLevel(logging.WARNING)
logging.getLogger("msal").setLevel(logging.WARNING)
logging.getLogger("transformers").setLevel(logging.WARNING)

logger = logging.getLogger("main")


def main():
    parser = argparse.ArgumentParser(
        description="SmartExpenseAgent — Automated Invoice Processing with DiT"
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single cycle and stop",
    )
    parser.add_argument(
        "--file",
        type=str,
        help="Process a single invoice file",
        metavar="FILE_PATH",
    )
    args = parser.parse_args()

    from agent.smart_expense_agent import SmartExpenseAgent
    agent = SmartExpenseAgent()

    # ── Mode 1: Single file ──────────────────────────────
    if args.file:
        file_path = Path(args.file)

        if not file_path.exists():
            logger.error(f"File not found: {file_path}")
            sys.exit(1)

        logger.info(f"Processing single file: {file_path.name}")

        invoice = agent._process(file_path)

        if invoice:
            print()
            print("=" * 60)
            print("PROCESSING RESULT")
            print("=" * 60)

            data = invoice.to_dict()
            for key, value in data.items():
                if value is not None:
                    print(f"  {key:<20} : {value}")

            print()
            print("-" * 60)
            print(f"  DiT Score  : {invoice.dit_confidence:.3f}" if invoice.dit_confidence else "  DiT Score  : N/A")
            print(f"  DiT Label  : {invoice.dit_label}")
            print(f"  Is Invoice : {invoice.dit_is_invoice}")
            print("-" * 60)
            print()

            agent.dataset_builder.add_invoice(invoice)

            exported = agent.exporter.export([invoice])
            print()
            for f in exported:
                print(f"  Report generated: {f}")

            if invoice.source_file:
                agent.exporter.move_to_valid_invoices(invoice.source_file)
                agent.exporter.cleanup_pending(invoice.source_file)

        else:
            print()
            print("Invoice could not be processed.")
            print(f"   Check: data/need_review/{file_path.name}")

    # ── Mode 2: Single cycle ─────────────────────────────
    elif args.once:
        logger.info("Single cycle mode.")
        summary = agent.run_cycle()

        print()
        print("=" * 60)
        print("CYCLE SUMMARY")
        print("=" * 60)
        print(f"  Total processed : {summary['total']}")
        print(f"  Validated       : {summary['validated']}")
        print(f"  Failed          : {summary['failed']}")
        print(f"  Excel reports   : {len(summary['exported'])}")
        for f in summary["exported"]:
            print(f"    → {f}")
        print()

    # ── Mode 3: Infinite loop (production) ───────────────
    else:
        logger.info("Production mode — infinite loop.")
        print("SmartExpenseAgent started in production mode.")
        print(f"Cycle interval: check app.log for details")
        print("Press Ctrl+C to stop.")
        agent.run()


if __name__ == "__main__":
    main()