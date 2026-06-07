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
# STATE est un singleton module-level → survivre aux reruns Streamlit
from utils.pipeline_state import STATE, add_event, reset

if not is_logged_in():
    st.switch_page("app.py")

DJANGO_URL = "http://localhost:8000/api"

# ── Hash store local persistant ───────────────────────────────────────────────
# Stocké dans data/processed_hashes.json dans la racine du projet agent.
# Survit aux redémarrages, indépendant de Django.
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
    """Retourne (est_doublon, hash_md5). Vérifie le store local ET Django."""
    h = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    content_hash = h.hexdigest()

    # 1. Vérification locale (plus rapide, toujours fiable)
    if content_hash in _load_hashes():
        return True, content_hash

    return False, content_hash

def _register_hash(content_hash: str):
    """Ajoute le hash au store local persistant."""
    hashes = _load_hashes()
    hashes.add(content_hash)
    _save_hashes(hashes)


# ── Helpers Django ────────────────────────────────────────────────────────────
def _file_md5(file_path: Path) -> str:
    """Compute MD5 hash of file content."""
    h = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _already_processed(file_path: Path, token: str) -> tuple[bool, str]:
    """Check if this file has already been processed (same content). Returns (exists, hash)."""
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
        "total_amount":        str(invoice.total_amount) if invoice.total_amount else None,
        "subtotal":            str(invoice.subtotal) if invoice.subtotal else None,
        "tax_amount":          str(invoice.tax_amount) if invoice.tax_amount else None,
        "currency":            invoice.currency or "MAD",
        "expense_category":    invoice.expense_category or "Other",
        "dit_confidence":      invoice.dit_confidence,
        "dit_label":           invoice.dit_label or "",
        "dit_is_invoice":      invoice.dit_is_invoice,
        "llm_confidence":      invoice.llm_confidence or "",
        "is_valid":            invoice.is_valid,
        "validation_errors":   invoice.validation_errors or [],
        "validation_warnings": invoice.validation_warnings or [],
        "attempt_count":       invoice.attempt_count,
        "status":              status_val,
        "source_filename":     filename,
        "source":              "email",
        "content_hash":        content_hash,
    }
    try:
        r = requests.post(f"{DJANGO_URL}/invoices/", json=data,
                          headers={"Authorization": f"Bearer {token}"}, timeout=15)
        if r.ok:
            return r.json().get("id")
    except Exception:
        pass
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


# Log handler: captures agent log messages and routes them to the UI activity feed
def _make_ui_log_handler():
    import logging

    AGENT_LOGGERS = {
        "tools.mail_fetcher_tool", "tools.document_verifier_tool",
        "tools.ocr_extraction_tool", "tools.ai_classifier_tool",
        "tools.validation_tool", "agent.smart_expense_agent",
    }
    TRANSLATIONS = [
        ("Searching for unread emails",      "📧", "Searching for unread emails with attachments..."),
        ("email(s) with attachments found",  "📬", "Email(s) with attachments found"),
        ("No documents to process",          "📭", "No new invoices in mailbox"),
        ("document(s) collected",            "📥", "Document(s) collected"),
        ("Invoice detected",                 "📨", "Invoice detected — downloading attachment"),
        ("Not an invoice",                   "🚫", "Email skipped — not an invoice"),
        ("DiT confirmed invoice",            "🔍", "DiT: document confirmed as invoice"),
        ("DiT rejected",                     "⚠️",  "DiT: document rejected — not an invoice"),
        ("OCR processing",                   "📝", "OCR extraction in progress..."),
        ("OCR successful",                   "📝", "OCR extraction successful"),
        ("LLM classification",               "🤖", "LLM classification in progress..."),
        ("Category :",                       "🏷️", "Category detected"),
        ("Validation passed",                "✅", "Validation passed"),
        ("Validation failed",                "❌", "Validation failed"),
        ("Definitive failure",               "❌", "Definitive failure after 3 attempts"),
        ("Processing:",                      "⚙️", "Processing file..."),
        ("Attempt",                          "🔁", "Retrying..."),
        ("Notification sent",                "📨", "Notification sent to accountant"),
        ("Email marked as read",             "✉️", "Email marked as read"),
    ]

    class UILogHandler(logging.Handler):
        def emit(self, record):
            if record.name not in AGENT_LOGGERS:
                return
            raw = record.getMessage()
            for fragment, icon, friendly in TRANSLATIONS:
                if fragment.lower() in raw.lower():
                    add_event(icon, (friendly or raw)[:90])
                    return
            if record.levelno >= logging.ERROR:
                add_event("💥", raw[:90])
            elif record.levelno >= logging.WARNING:
                add_event("⚠️", raw[:90])

    return UILogHandler()


# ── Thread principal du pipeline ──────────────────────────────────────────────
def _run_continuous(agent, stop_event: threading.Event, interval_minutes: int, token: str):
    import logging

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
                add_event("🔄", f"─── Cycle #{STATE['cycles']} ───")

                files = agent.mail_fetcher.fetch_invoices()

                if files:
                    add_event("📥", f"{len(files)} fichier(s) à traiter")

                validated = []
                for file_path in files:
                    STATE["current_file"] = file_path.name

                    # ── Vérification doublon (store local JSON) ────────────
                    duplicate, content_hash = _is_duplicate(file_path)
                    if duplicate:
                        add_event("⏭️", f"Doublon ignoré : déjà traité (hash={content_hash[:8]}...)")
                        file_path.unlink(missing_ok=True)
                        continue

                    invoice = agent._process(file_path)
                    if invoice:
                        vendor = invoice.vendor_name or "Inconnu"
                        amount = f"{invoice.total_amount} {invoice.currency}" if invoice.total_amount else "—"
                        validated.append(invoice)
                        # Enregistrer le hash AVANT de sauvegarder (évite race condition)
                        _register_hash(content_hash)
                        inv_id = _save_invoice_to_django(invoice, file_path.name, token,
                                                          content_hash=content_hash)
                        exported = agent.exporter.export([invoice])
                        if inv_id and exported:
                            _upload_excel_to_django(inv_id, str(exported[0]), token)
                            add_event("📊", f"Excel disponible : {vendor} | {amount}")
                    else:
                        # Même en cas d'échec, enregistrer pour ne pas retenter indéfiniment
                        _register_hash(content_hash)
                        add_event("🗂️", f"{file_path.name} → révision manuelle")

                failed = len(files) - len(validated)
                STATE["total"]     += len(files)
                STATE["validated"] += len(validated)
                STATE["failed"]    += failed
                STATE["current_file"] = ""

                if files:
                    add_event("✔️", f"Cycle #{STATE['cycles']}: {len(validated)} validated, {failed} failed")

            except Exception as e:
                add_event("💥", f"Error: {str(e)[:80]}")

            if not stop_event.is_set():
                add_event("⏳", f"Next cycle in {interval_minutes} min...")
            stop_event.wait(timeout=interval_minutes * 60)

    finally:
        for lg in attached:
            lg.removeHandler(ui_handler)
        STATE["running"] = False
        add_event("⏹️", "Pipeline stopped.")


# Sidebar
with st.sidebar:
    st.markdown(f"### 🏢 {st.session_state.get('company_name', '')}")
    st.markdown("---")
    st.page_link("pages/1_Dashboard.py",      label="📊 Dashboard")
    st.page_link("pages/2_Upload.py",          label="📤 Upload Invoice")
    st.page_link("pages/3_Pipeline.py",        label="🚀 Run Pipeline")
    st.page_link("pages/4_Telechargements.py", label="📥 Downloads")
    st.markdown("---")
    if st.button("🚪 Sign Out", use_container_width=True):
        logout()
        st.switch_page("app.py")

# Header
st.title("🚀 Email Pipeline")
st.caption("The agent connects to your mailbox, detects invoices, and processes them automatically")

with st.expander("ℹ️ How does the pipeline work?", expanded=False):
    st.markdown("""
    1. **📧 Outlook Connection** — Connects via Microsoft Graph API (OAuth2)
    2. **🔎 LLM Filtering** — Each email is analyzed to detect invoices
    3. **🔍 DiT Visual Check** — Visual document verification
    4. **📝 Azure OCR** — Field extraction: vendor, date, amount...
    5. **🤖 LLM Classification** — Categorization and data reformatting
    6. **✅ Validation** — 12 business rules applied
    7. **📊 Excel Export** — Report available in **Downloads**
    """)

st.markdown("---")

# Mode selection
col_mode1, col_mode2 = st.columns(2)

with col_mode1:
    st.markdown("### 🔄 Single Cycle")
    st.caption("Processes all pending unread emails, then stops.")
    run_once = st.button("▶️ Run One Cycle", type="primary",
                          use_container_width=True, key="btn_once",
                          disabled=STATE["running"])

with col_mode2:
    st.markdown("### ♾️ Continuous Mode")
    st.caption("Runs in a loop and checks for new emails periodically.")
    interval_cont = st.number_input("Interval (min)", min_value=1, max_value=60,
                                     value=5, key="interval_cont",
                                     disabled=STATE["running"])
    if not STATE["running"]:
        if st.button("🔁 Start Continuous", use_container_width=True,
                     type="primary", key="btn_loop"):
            try:
                agent_root = Path(__file__).resolve().parent.parent.parent
                sys.path.insert(0, str(agent_root))
                from agent.smart_expense_agent import SmartExpenseAgent
                agent = SmartExpenseAgent()

                token    = st.session_state.get("access_token", "")
                stop_evt = threading.Event()
                reset(interval_minutes=int(interval_cont), stop_evt=stop_evt)

                # Immediate events before the first cycle
                add_event("🚀", "Pipeline started")
                add_event("⚙️", "Loading AI models (DiT, OCR, LLM)...")

                threading.Thread(
                    target=_run_continuous,
                    args=(agent, stop_evt, int(interval_cont), token),
                    daemon=True,
                ).start()
                st.rerun()

            except ImportError:
                st.error("Agent not available. Run Streamlit from the project root.")
    else:
        if st.button("⏹️ Stop Pipeline", type="primary",
                     use_container_width=True, key="btn_stop"):
            STATE["stop_evt"].set()
            STATE["running"] = False
            add_event("⏹️", "Stop requested by user...")
            st.rerun()

st.markdown("---")

# Continuous mode — dedicated display area
if STATE["running"] or (STATE["events"] and not run_once):

    st.markdown("### 🟢 Pipeline Running" if STATE["running"] else "### ⏹️ Last Session")

    # Counters
    kc1, kc2, kc3, kc4 = st.columns(4)
    kc1.metric("🔄 Cycles",    STATE["cycles"])
    kc2.metric("📋 Processed", STATE["total"])
    kc3.metric("✅ Validated",  STATE["validated"])
    kc4.metric("❌ Failed",     STATE["failed"])

    if STATE["current_file"]:
        st.info(f"⚙️ Processing: `{STATE['current_file']}`")

    # Simplified events: icon + message only, no timestamp or hash
    ICONS_OK  = {"✅", "✔️", "📊", "✉️"}
    ICONS_ERR = {"❌", "💥", "🗂️"}

    events = STATE["events"]
    if events:
        # Show only current cycle events (since the last "🔄")
        current_cycle_events = []
        for line in events:
            current_cycle_events.append(line)
            if "🔄" in line and "Cycle" in line and len(current_cycle_events) > 1:
                break

        for line in current_cycle_events[:12]:
            parts = line.split("  ", 2)
            if len(parts) == 3:
                icon = parts[1].strip()
                msg  = parts[2].strip()
                if "hash=" in msg:
                    msg = msg.split("(hash=")[0].strip()
            else:
                icon, msg = "ℹ️", line

            display = f"{icon}  {msg}"
            if icon in ICONS_OK:
                st.success(display)
            elif icon in ICONS_ERR:
                st.error(display)
            else:
                st.info(display)

    # Auto-refresh every 2s
    if STATE["running"]:
        time.sleep(2)
        st.rerun()

    st.stop()  # Prevent single cycle section from showing below

st.markdown("---")

# Single cycle mode
if run_once:
    token = st.session_state.get("access_token", "")
    try:
        agent_root = Path(__file__).resolve().parent.parent.parent
        sys.path.insert(0, str(agent_root))
        from agent.smart_expense_agent import SmartExpenseAgent
        agent = SmartExpenseAgent()
    except ImportError:
        st.error("❌ Agent not available.")
        st.stop()

    with st.status("📧 Connecting to mailbox...", expanded=True) as status_box:
        st.write("Searching for unread emails with attachments...")
        try:
            files = agent.mail_fetcher.fetch_invoices()
        except Exception as e:
            st.error(f"Error: {e}")
            st.stop()

        if not files:
            status_box.update(label="📭 No new invoices found", state="complete")
            st.info("No invoice emails found in the mailbox.")
            st.stop()

        st.write(f"✅ **{len(files)}** file(s) detected")
        status_box.update(label=f"📧 {len(files)} invoice(s) retrieved", state="complete")

    st.markdown(f"### Processing {len(files)} invoice(s)")
    progress_bar       = st.progress(0)
    validated_invoices = []
    failed_files       = []
    excel_downloads    = []

    for i, file_path in enumerate(files):
        progress_bar.progress(int((i / len(files)) * 100),
                              text=f"Processing {i+1}/{len(files)}: `{file_path.name}`")

        # Duplicate check (local JSON hash store)
        duplicate, content_hash = _is_duplicate(file_path)
        if duplicate:
            st.warning(f"⏭️ `{file_path.name}` — duplicate ignored (already processed)")
            file_path.unlink(missing_ok=True)
            continue

        with st.spinner(f"Processing `{file_path.name}`..."):
            invoice = agent._process(file_path)

        if invoice:
            icon   = "✅" if invoice.is_valid else "🔍"
            vendor = invoice.vendor_name or "Unknown"
            amount = f"{invoice.total_amount} {invoice.currency}" if invoice.total_amount else "—"
            st.success(f"{icon} **{vendor}** | {invoice.invoice_date or '—'} | {amount} | {invoice.expense_category or '—'}")
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
        else:
            _register_hash(content_hash)
            st.error(f"❌ `{file_path.name}` — moved to manual review")
            failed_files.append(file_path.name)

    progress_bar.progress(100, text="Cycle complete!")

    st.markdown("---")
    st.markdown("### 📋 Summary")
    c1, c2, c3 = st.columns(3)
    c1.metric("📋 Total",     len(files))
    c2.metric("✅ Validated", len(validated_invoices))
    c3.metric("❌ Failed",    len(failed_files))

    if excel_downloads:
        st.success(f"📊 {len(excel_downloads)} Excel report(s) available in **Downloads**")
        for excel_path, vendor in excel_downloads:
            fname = os.path.basename(str(excel_path))
            try:
                with open(str(excel_path), "rb") as fh:
                    st.download_button(label=f"📥 {fname}", data=fh.read(),
                                       file_name=fname, key=f"dl_{fname}_{time.time()}",
                                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            except Exception:
                pass

    if failed_files:
        with st.expander(f"🔍 {len(failed_files)} file(s) needing manual review"):
            for f in failed_files:
                st.write(f"• `{f}`")
