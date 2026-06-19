"""
Page 3 — Lancer le pipeline email complet
"""
import streamlit as st
import sys, os, time, threading, requests, hashlib
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

st.set_page_config(page_title="Pipeline Email", layout="wide")
st.markdown("<style>[data-testid='stSidebarNav']{display:none}</style>", unsafe_allow_html=True)

from utils.api import is_logged_in, logout
from utils.session import restore_session
from utils.pipeline_state import STATE, add_event, reset

restore_session()
if not is_logged_in():
    st.switch_page("app.py")

DJANGO_URL = "http://localhost:8000/api"

import json as _json

def _hash_store_path() -> Path:
    root = Path(__file__).resolve().parent.parent.parent
    store = root / "data" / "processed_hashes.json"
    store.parent.mkdir(parents=True, exist_ok=True)
    return store

def _load_hashes() -> set:
    p = _hash_store_path()
    try:
        return set(_json.loads(p.read_text(encoding="utf-8")))
    except Exception:
        return set()

def _save_hashes(hashes: set):
    _hash_store_path().write_text(
        _json.dumps(list(hashes), indent=2), encoding="utf-8"
    )

def _is_duplicate(file_path: Path) -> tuple[bool, str]:
    h = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    content_hash = h.hexdigest()
    if content_hash in _load_hashes():
        return True, content_hash
    return False, content_hash

def _register_hash(content_hash: str):
    hashes = _load_hashes()
    hashes.add(content_hash)
    _save_hashes(hashes)


def _file_md5(file_path: Path) -> str:
    h = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _already_processed(file_path: Path, token: str) -> tuple[bool, str]:
    content_hash = _file_md5(file_path)
    try:
        r = requests.get(
            f"{DJANGO_URL}/invoices/check_hash/",
            headers={"Authorization": f"Bearer {token}"},
            params={"hash": content_hash},
            timeout=10,
        )
        if r.ok and r.json().get("exists", False):
            return True, content_hash
    except Exception:
        pass
    return False, content_hash


def _save_invoice_to_django(invoice, filename: str, token: str,
                             content_hash: str = "") -> int | None:
    status_val = "validated" if invoice.is_valid else "need_review"
    if not invoice.dit_is_invoice:
        status_val = "rejected"
    data = {
        "vendor_name":         invoice.vendor_name or "",
        "invoice_date":        invoice.invoice_date or "",
        "invoice_id":          invoice.invoice_id or "",
        "total_amount":        float(invoice.total_amount) if invoice.total_amount else None,
        "subtotal":            float(invoice.subtotal) if invoice.subtotal else None,
        "tax_amount":          float(invoice.tax_amount) if invoice.tax_amount else None,
        "currency":            invoice.currency or "MAD",
        "expense_category":    invoice.expense_category or "Other",
        "dit_confidence":      float(invoice.dit_confidence) if invoice.dit_confidence is not None else None,
        "dit_label":           invoice.dit_label or "",
        "dit_is_invoice":      bool(invoice.dit_is_invoice) if invoice.dit_is_invoice is not None else False,
        "llm_confidence":      invoice.llm_confidence or "",
        "is_valid":            bool(invoice.is_valid) if invoice.is_valid is not None else False,
        "validation_errors":   invoice.validation_errors or [],
        "validation_warnings": invoice.validation_warnings or [],
        "attempt_count":       int(invoice.attempt_count) if invoice.attempt_count else 1,
        "status":              status_val,
        "source_filename":     filename,
        "source":              "email",
        "content_hash":        content_hash,
    }
    try:
        r = requests.post(
            f"{DJANGO_URL}/invoices/",
            json=data,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            timeout=15,
        )
        if r.ok:
            return r.json().get("id")
        else:
            add_event("", f"[DB ERROR] {r.status_code}: {r.text[:200]}")
    except Exception as e:
        add_event("", f"[DB ERROR] {str(e)[:150]}")
    return None


def _save_invoice_to_django_raw(data: dict, token: str) -> int | None:
    """Save a raw dict (no Invoice object) directly to the DB."""
    try:
        r = requests.post(
            f"{DJANGO_URL}/invoices/",
            json=data,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            timeout=15,
        )
        if r.ok:
            return r.json().get("id")
        else:
            add_event("", f"[DB ERROR] {r.status_code}: {r.text[:200]}")
    except Exception as e:
        add_event("", f"[DB ERROR] {str(e)[:150]}")
    return None


def _upload_excel_to_django(invoice_id: int, excel_path: str, token: str):
    try:
        with open(excel_path, "rb") as f:
            requests.post(
                f"{DJANGO_URL}/invoices/{invoice_id}/upload_excel/",
                headers={"Authorization": f"Bearer {token}"},
                files={"excel_file": (os.path.basename(excel_path), f,
                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
                timeout=20,
            )
    except Exception:
        pass


def _upload_document_to_django(invoice_id: int, file_path: Path, token: str):
    """Upload le fichier original pour permettre la prévisualisation dans Document Review."""
    try:
        ext  = file_path.suffix.lower()
        mime = {".pdf": "application/pdf", ".png": "image/png",
                ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}.get(ext, "application/octet-stream")
        with open(file_path, "rb") as f:
            requests.post(
                f"{DJANGO_URL}/invoices/{invoice_id}/upload_document/",
                headers={"Authorization": f"Bearer {token}"},
                files={"document": (file_path.name, f, mime)},
                timeout=20,
            )
    except Exception:
        pass


def _make_ui_log_handler():
    import logging

    AGENT_LOGGERS = {
        "tools.mail_fetcher_tool", "tools.document_verifier_tool",
        "tools.ocr_extraction_tool", "tools.ai_classifier_tool",
        "tools.validation_tool", "agent.smart_expense_agent",
    }
    TRANSLATIONS = [
        ("Searching for unread emails",      "", "Searching for unread emails with attachments..."),
        ("email(s) with attachments found",  "", "Email(s) with attachments found"),
        ("No documents to process",          "", "No new invoices in mailbox"),
        ("document(s) collected",            "", "Document(s) collected"),
        ("Invoice detected",                 "", "Invoice detected — downloading attachment"),
        ("Not an invoice",                   "", "Email skipped — not an invoice"),
        ("DiT confirmed invoice",            "", "DiT: document confirmed as invoice"),
        ("DiT rejected",                     "",  "DiT: document rejected — not an invoice"),
        ("OCR processing",                   "", "OCR extraction in progress..."),
        ("OCR successful",                   "", "OCR extraction successful"),
        ("LLM classification",               "", "LLM classification in progress..."),
        ("Category :",                       "", "Category detected"),
        ("Validation passed",                "", "Validation passed"),
        ("Validation failed",                "", "Validation failed"),
        ("Definitive failure",               "", "Definitive failure after 3 attempts"),
        ("Processing:",                      "", "Processing file..."),
        ("Attempt",                          "", "Retrying..."),
        ("Notification sent",                "", "Notification sent to accountant"),
        ("Email marked as read",             "", "Email marked as read"),
    ]

    class UILogHandler(logging.Handler):
        def emit(self, record):
            if record.name not in AGENT_LOGGERS:
                return
            raw = record.getMessage()
            for fragment, icon, friendly in TRANSLATIONS:
                if fragment.lower() in raw.lower():
                    add_event("", (friendly or raw)[:90])
                    return
            if record.levelno >= logging.ERROR:
                add_event("", raw[:90])
            elif record.levelno >= logging.WARNING:
                add_event("", raw[:90])

    return UILogHandler()


def _run_continuous(agent, stop_event: threading.Event, interval_minutes: int, token: str):
    import logging, traceback

    agent_root = str(Path(__file__).resolve().parent.parent.parent)
    if agent_root not in sys.path:
        sys.path.insert(0, agent_root)

    ui_handler = _make_ui_log_handler()
    ui_handler.setLevel(logging.INFO)
    attached = []
    for name in ["tools.mail_fetcher_tool", "tools.document_verifier_tool",
                 "tools.ocr_extraction_tool", "tools.ai_classifier_tool",
                 "tools.validation_tool", "agent.smart_expense_agent"]:
        lg = logging.getLogger(name)
        lg.addHandler(ui_handler)
        attached.append(lg)

    try:
        while not stop_event.is_set():
            try:
                STATE["cycles"] += 1
                add_event("", f"--- Cycle #{STATE['cycles']} ---")

                files = agent.mail_fetcher.fetch_invoices()

                if files:
                    add_event("", f"{len(files)} file(s) to process")

                validated = []
                for file_path in files:
                    STATE["current_file"] = file_path.name

                    duplicate, content_hash = _is_duplicate(file_path)
                    if duplicate:
                        add_event("", f"Duplicate ignored: already processed (hash={content_hash[:8]}...)")
                        try:
                            agent.mail_fetcher.mark_as_validated(file_path)
                        except Exception:
                            pass
                        file_path.unlink(missing_ok=True)
                        continue

                    invoice = agent._process(file_path)
                    if invoice and invoice.dit_is_invoice:
                        vendor = invoice.vendor_name or "Unknown"
                        amount = f"{invoice.total_amount} {invoice.currency}" if invoice.total_amount else "-"
                        validated.append(invoice)
                        _register_hash(content_hash)
                        inv_id = _save_invoice_to_django(invoice, file_path.name, token,
                                                          content_hash=content_hash)
                        exported = agent.exporter.export([invoice])
                        if inv_id and exported:
                            _upload_excel_to_django(inv_id, str(exported[0]), token)
                            add_event("", f"Excel available: {vendor} | {amount}")
                        agent.exporter.move_to_valid_invoices(file_path)
                        agent.exporter.cleanup_pending(file_path)
                        agent.mail_fetcher.mark_as_validated(file_path)
                    elif invoice and not invoice.dit_is_invoice:
                        _register_hash(content_hash)
                        inv_id = _save_invoice_to_django(invoice, file_path.name, token,
                                                         content_hash=content_hash)
                        if inv_id and file_path.exists():
                            _upload_document_to_django(inv_id, file_path, token)
                        try:
                            agent.mail_fetcher.mark_as_validated(file_path)
                        except Exception:
                            pass
                        STATE["rejected"] += 1
                        add_event("", f"DiT rejected (score={invoice.dit_confidence:.3f}): {file_path.name}")
                    else:
                        _register_hash(content_hash)
                        need_review_path = agent.exporter.move_to_need_review(file_path)
                        try:
                            agent.mail_fetcher.mark_as_rejected(file_path)
                        except Exception:
                            pass
                        raw_id = _save_invoice_to_django_raw({
                            "vendor_name": "", "invoice_date": "", "invoice_id": "",
                            "total_amount": None, "subtotal": None, "tax_amount": None,
                            "currency": "MAD", "expense_category": "Other",
                            "dit_confidence": None, "dit_label": "", "dit_is_invoice": True,
                            "llm_confidence": "", "is_valid": False,
                            "validation_errors": ["Processing failed — manual review required"],
                            "validation_warnings": [],
                            "attempt_count": 3, "status": "need_review",
                            "source_filename": file_path.name, "source": "email",
                            "content_hash": content_hash,
                        }, token)
                        if raw_id:
                            dest = Path("data/need_review") / file_path.name
                            if dest.exists():
                                _upload_document_to_django(raw_id, dest, token)
                        add_event("", f"{file_path.name} -> need review (saved to DB)")

                failed = len(files) - len(validated)
                STATE["total"]     += len(files)
                STATE["validated"] += len(validated)
                STATE["failed"]    += failed
                STATE["current_file"] = ""

                # System Handling Rate — mis à jour après chaque cycle
                _total = STATE["total"]
                _rate  = round(STATE["validated"] / _total * 100, 1) if _total > 0 else 0.0

                if files:
                    add_event("", f"Cycle #{STATE['cycles']}: {len(validated)} validated, {failed} failed | Handling Rate: {_rate}%")

            except Exception as e:
                tb = traceback.format_exc()
                short = str(e)[:120]
                add_event("", f"Error: {short}")
                STATE["last_error"] = tb

            if not stop_event.is_set():
                add_event("", f"Next cycle in {interval_minutes} min...")
            stop_event.wait(timeout=interval_minutes * 60)

    finally:
        for lg in attached:
            lg.removeHandler(ui_handler)
        STATE["running"] = False
        add_event("", "Pipeline stopped.")


# Sidebar
with st.sidebar:
    st.markdown(f"### {st.session_state.get('company_name', '')}")
    st.markdown("---")
    st.page_link("pages/1_Dashboard.py",      label="Dashboard")
    st.page_link("pages/2_Upload.py",          label="Upload Invoice")
    st.page_link("pages/3_Pipeline.py",        label="Run Pipeline")
    st.page_link("pages/4_Telechargements.py", label="Downloads")
    st.markdown("---")
    if st.button("Sign Out", use_container_width=True):
        logout()
        st.switch_page("app.py")

# Header
st.title("Email Pipeline")
st.caption("The agent connects to your mailbox, detects invoices, and processes them automatically")

with st.expander("How does the pipeline work?", expanded=False):
    st.markdown("""
    1. **Outlook Connection** — Connects via Microsoft Graph API (OAuth2)
    2. **LLM Filtering** — Each email is analyzed to detect invoices
    3. **DiT Visual Check** — Visual document verification
    4. **Azure OCR** — Field extraction: vendor, date, amount...
    5. **LLM Classification** — Categorization and data reformatting
    6. **Validation** — 12 business rules applied
    7. **Excel Export** — Report available in **Downloads**
    """)

st.markdown("---")

col_mode1, col_mode2 = st.columns(2)

with col_mode1:
    st.markdown("### Single Cycle")
    st.caption("Processes all pending unread emails, then stops.")
    run_once = st.button("Run One Cycle", type="primary",
                          use_container_width=True, key="btn_once",
                          disabled=STATE["running"])

with col_mode2:
    st.markdown("### Continuous Mode")
    st.caption("Runs in a loop and checks for new emails periodically.")
    interval_cont = st.number_input("Interval (min)", min_value=1, max_value=60,
                                     value=5, key="interval_cont",
                                     disabled=STATE["running"])
    if not STATE["running"]:
        if st.button("Start Continuous", use_container_width=True,
                     type="primary", key="btn_loop"):
            try:
                agent_root = Path(__file__).resolve().parent.parent.parent
                sys.path.insert(0, str(agent_root))
                from agent.smart_expense_agent import SmartExpenseAgent
                agent = SmartExpenseAgent()

                token    = st.session_state.get("access_token", "")
                stop_evt = threading.Event()
                reset(interval_minutes=int(interval_cont), stop_evt=stop_evt)

                add_event("", "Pipeline started")
                add_event("", "Loading AI models (DiT, OCR, LLM)...")

                threading.Thread(
                    target=_run_continuous,
                    args=(agent, stop_evt, int(interval_cont), token),
                    daemon=True,
                ).start()
                st.rerun()

            except ImportError:
                st.error("Agent not available. Run Streamlit from the project root.")
    else:
        if st.button("Stop Pipeline", type="primary",
                     use_container_width=True, key="btn_stop"):
            STATE["stop_evt"].set()
            STATE["running"] = False
            add_event("", "Stop requested by user...")
            st.rerun()

st.markdown("---")

if STATE["running"] or (STATE["events"] and not run_once):

    st.markdown("### Pipeline Running" if STATE["running"] else "### Last Session")

    auth_msg = STATE.get("auth_message", "")
    if auth_msg:
        st.warning("Microsoft authentication required")
        st.code(auth_msg, language=None)
        st.info("Open the URL above, enter the code, then sign in with your Microsoft account. The pipeline will continue automatically.")

    _t = STATE["total"]
    _handling_rate = round(STATE["validated"] / _t * 100, 1) if _t > 0 else 0.0

    kc1, kc2, kc3, kc4, kc5 = st.columns(5)
    kc1.metric("Cycles",         STATE["cycles"])
    kc2.metric("Processed",      _t)
    kc3.metric("Validated",      STATE["validated"])
    kc4.metric("Failed",         STATE["failed"])
    kc5.metric("Handling Rate",  f"{_handling_rate}%",
               help="validated / total processed")

    if STATE.get("last_error"):
        with st.expander("Last error — click to see details"):
            st.code(STATE["last_error"], language="python")

    if STATE["current_file"]:
        st.info(f"Processing: `{STATE['current_file']}`")

    events = STATE["events"]
    if events:
        current_cycle_events = []
        for line in events:
            current_cycle_events.append(line)
            if "Cycle" in line and len(current_cycle_events) > 1:
                break

        for line in current_cycle_events[:12]:
            parts = line.split("  ", 2)
            msg = parts[2].strip() if len(parts) == 3 else line
            if "hash=" in msg:
                msg = msg.split("(hash=")[0].strip()
            st.info(msg)

    if STATE["running"]:
        time.sleep(2)
        st.rerun()

    st.stop()

st.markdown("---")

if run_once:
    token = st.session_state.get("access_token", "")
    try:
        agent_root = Path(__file__).resolve().parent.parent.parent
        sys.path.insert(0, str(agent_root))
        from agent.smart_expense_agent import SmartExpenseAgent
        agent = SmartExpenseAgent()
    except ImportError:
        st.error("Agent not available.")
        st.stop()

    with st.status("Connecting to mailbox...", expanded=True) as status_box:
        st.write("Searching for unread emails with attachments...")
        try:
            files = agent.mail_fetcher.fetch_invoices()
        except Exception as e:
            st.error(f"Error: {e}")
            st.stop()

        if not files:
            status_box.update(label="No new invoices found", state="complete")
            st.info("No invoice emails found in the mailbox.")
            st.stop()

        st.write(f"**{len(files)}** file(s) detected")
        status_box.update(label=f"{len(files)} invoice(s) retrieved", state="complete")

    st.markdown(f"### Processing {len(files)} invoice(s)")
    progress_bar       = st.progress(0)
    validated_invoices = []
    failed_files       = []
    excel_downloads    = []

    for i, file_path in enumerate(files):
        progress_bar.progress(int((i / len(files)) * 100),
                              text=f"Processing {i+1}/{len(files)}: `{file_path.name}`")

        duplicate, content_hash = _is_duplicate(file_path)
        if duplicate:
            st.warning(f"`{file_path.name}` — duplicate ignored (already processed)")
            try:
                agent.mail_fetcher.mark_as_validated(file_path)
            except Exception:
                pass
            file_path.unlink(missing_ok=True)
            continue

        with st.spinner(f"Processing `{file_path.name}`..."):
            invoice = agent._process(file_path)

        if invoice and invoice.dit_is_invoice:
            vendor = invoice.vendor_name or "Unknown"
            amount = f"{invoice.total_amount} {invoice.currency}" if invoice.total_amount else "-"
            status_label = "Validated" if invoice.is_valid else "Review needed"
            st.success(f"{status_label} | {vendor} | {invoice.invoice_date or '-'} | {amount} | {invoice.expense_category or '-'}")
            validated_invoices.append(invoice)
            _register_hash(content_hash)
            inv_id   = _save_invoice_to_django(invoice, file_path.name, token,
                                               content_hash=content_hash)
            exported = agent.exporter.export([invoice])
            agent.dataset_builder.add_invoice(invoice)
            if inv_id and exported:
                _upload_excel_to_django(inv_id, str(exported[0]), token)
                excel_downloads.append((exported[0], vendor))
            if invoice.source_file:
                agent.exporter.move_to_valid_invoices(invoice.source_file)
                agent.exporter.cleanup_pending(invoice.source_file)
                agent.mail_fetcher.mark_as_validated(invoice.source_file)
        elif invoice and not invoice.dit_is_invoice:
            _register_hash(content_hash)
            _save_invoice_to_django(invoice, file_path.name, token, content_hash=content_hash)
            st.warning(f"`{file_path.name}` — rejected by DiT (score={invoice.dit_confidence:.3f}, high confidence)")
            failed_files.append(file_path.name)
        else:
            _register_hash(content_hash)
            _save_invoice_to_django_raw({
                "vendor_name": "", "invoice_date": "", "invoice_id": "",
                "total_amount": None, "subtotal": None, "tax_amount": None,
                "currency": "MAD", "expense_category": "Other",
                "dit_confidence": None, "dit_label": "", "dit_is_invoice": True,
                "llm_confidence": "", "is_valid": False,
                "validation_errors": ["Processing failed — manual review required"],
                "validation_warnings": [],
                "attempt_count": 3, "status": "need_review",
                "source_filename": file_path.name, "source": "email",
                "content_hash": content_hash,
            }, token)
            st.error(f"`{file_path.name}` — moved to manual review")
            failed_files.append(file_path.name)

    progress_bar.progress(100, text="Cycle complete!")

    st.markdown("---")
    st.markdown("### Summary")
    c1, c2, c3 = st.columns(3)
    c1.metric("Total",     len(files))
    c2.metric("Validated", len(validated_invoices))
    c3.metric("Failed",    len(failed_files))

    if excel_downloads:
        st.success(f"{len(excel_downloads)} Excel report(s) available in Downloads")
        for excel_path, vendor in excel_downloads:
            fname = os.path.basename(str(excel_path))
            try:
                with open(str(excel_path), "rb") as fh:
                    st.download_button(label=fname, data=fh.read(),
                                       file_name=fname, key=f"dl_{fname}_{time.time()}",
                                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            except Exception:
                pass

    if failed_files:
        with st.expander(f"{len(failed_files)} file(s) needing manual review"):
            for f in failed_files:
                st.write(f"- `{f}`")
