"""
Page 2 — Direct invoice upload (multi-file)
"""
import streamlit as st
import tempfile, os, sys, time, hashlib
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

st.set_page_config(page_title="Upload Invoice", layout="wide")
st.markdown("<style>[data-testid='stSidebarNav']{display:none}</style>", unsafe_allow_html=True)

from utils.api import is_logged_in, save_invoice, upload_excel, upload_document, logout, check_invoice_hash
from utils.session import restore_session

restore_session()
if not is_logged_in():
    st.switch_page("app.py")

# Sidebar
with st.sidebar:
    st.markdown(f"### {st.session_state.get('company_name', '')}")
    st.markdown("---")
    st.page_link("pages/1_Dashboard.py",      label="Dashboard")
    st.page_link("pages/2_Upload.py",          label="Upload Invoice")
    st.page_link("pages/3_Pipeline.py",        label="Run Pipeline")
    st.page_link("pages/4_Telechargements.py", label="Downloads")
    st.page_link("pages/5_Review.py",          label="Document Review")
    st.markdown("---")
    if st.button("Sign Out", use_container_width=True):
        logout()
        st.switch_page("app.py")

# Header
st.title("Upload Invoice")
st.caption("Upload one or more PDF or image files — the agent processes each one immediately")

# File uploader — multi-file
uploaded_files = st.file_uploader(
    "Drag and drop your invoices here",
    type=["pdf", "jpg", "jpeg", "png"],
    accept_multiple_files=True,
    help="Accepted formats: PDF, JPG, JPEG, PNG — max 10 MB per file",
)

if not uploaded_files:
    st.markdown("""
    <div style="background:#f8f9fa; border-radius:12px; padding:2rem; text-align:center; color:#666; margin-top:2rem;">
      <h3>How does it work?</h3>
      <div style="display:grid; grid-template-columns:1fr 1fr 1fr 1fr; gap:1rem; margin-top:1rem;">
        <div><b>1. DiT Vision</b><br>Visually verifies the document is an invoice</div>
        <div><b>2. Azure OCR</b><br>Extracts all fields (vendor, amount, date...)</div>
        <div><b>3. LLM</b><br>Classifies the expense and reformats data</div>
        <div><b>4. Validation</b><br>Applies 12 business rules and generates Excel report</div>
      </div>
    </div>
    """, unsafe_allow_html=True)
    st.stop()

# Summary of selected files
st.markdown("---")
st.subheader(f"{len(uploaded_files)} file(s) selected")
for f in uploaded_files:
    st.markdown(f"- `{f.name}` — {f.size / 1024:.1f} KB")

if not st.button("Process All Invoices", type="primary", use_container_width=True):
    st.stop()

# Load agent once
agent_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(agent_root))

try:
    from agent.smart_expense_agent import SmartExpenseAgent
    cache_key = f"agent_{st.session_state.get('company_id')}"
    if cache_key not in st.session_state:
        with st.spinner("Loading DiT model..."):
            st.session_state[cache_key] = SmartExpenseAgent(company_id=st.session_state.get("company_id"))
    agent = st.session_state[cache_key]
    demo_mode = False
except ImportError:
    agent = None
    demo_mode = True

# Process each file
results = []

for idx, uploaded in enumerate(uploaded_files):
    st.markdown("---")
    st.markdown(f"### [{idx+1}/{len(uploaded_files)}] `{uploaded.name}`")

    file_bytes   = uploaded.read()
    content_hash = hashlib.md5(file_bytes).hexdigest()

    # Duplicate check
    if check_invoice_hash(content_hash):
        st.warning("Duplicate detected — this invoice has already been processed. Skipped.")
        results.append((uploaded.name, "duplicate", None, [], content_hash))
        continue

    suffix   = Path(uploaded.name).suffix.lower()
    tmp_path = None

    progress_bar = st.progress(0)
    status_text  = st.empty()

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(file_bytes)
            tmp_path = Path(tmp.name)

        if demo_mode:
            for i in range(5):
                status_text.markdown(f"**Step {i+1}/5...**")
                progress_bar.progress((i + 1) * 20)
                time.sleep(0.4)
            invoice  = None
            exported = []
        else:
            status_text.markdown("**Processing... (DiT + OCR + LLM — may take a few minutes)**")
            progress_bar.progress(20)
            invoice = agent._process(tmp_path)
            progress_bar.progress(90)

            if invoice and invoice.dit_is_invoice:
                status_text.markdown("**Generating Excel report...**")
                exported = agent.exporter.export([invoice])
                agent.dataset_builder.add_invoice(invoice)
            else:
                exported = []

            progress_bar.progress(100)

        status_text.empty()

    except Exception as e:
        progress_bar.progress(100)
        status_text.empty()
        st.warning(f"Processing interrupted — document sent to manual review. ({type(e).__name__}: {str(e)[:150]})")
        save_invoice({
            "vendor_name": "", "invoice_date": "", "invoice_id": "",
            "total_amount": None, "subtotal": None, "tax_amount": None,
            "currency": "MAD", "expense_category": "Other",
            "dit_confidence": None, "dit_label": "", "dit_is_invoice": True,
            "llm_confidence": "", "is_valid": False,
            "validation_errors": [f"Unexpected error: {type(e).__name__}: {str(e)[:200]}"],
            "validation_warnings": [], "attempt_count": 3, "status": "need_review",
            "source_filename": uploaded.name, "source": "upload",
            "content_hash": content_hash,
        })
        results.append((uploaded.name, "error", None, [], content_hash))
        if tmp_path:
            tmp_path.unlink(missing_ok=True)
        continue
    finally:
        if tmp_path:
            tmp_path.unlink(missing_ok=True)

    # Individual result display
    if not invoice:
        st.warning("This invoice could not be processed automatically and has been sent for manual review.")
        if agent:
            try:
                sent = agent.mail_fetcher.notify_accountant(
                    filename=uploaded.name,
                    errors=["Processing failed after maximum retries — manual review required"],
                )
                if sent:
                    st.info(f"Accountant notified by email.")
                else:
                    st.caption("(Accountant email not sent — Microsoft not authenticated)")
            except Exception:
                pass
        db_result = save_invoice({
            "vendor_name": "", "invoice_date": "", "invoice_id": "",
            "total_amount": None, "subtotal": None, "tax_amount": None,
            "currency": "MAD", "expense_category": "Other",
            "dit_confidence": None, "dit_label": "", "dit_is_invoice": True,
            "llm_confidence": "", "is_valid": False,
            "validation_errors": ["Processing failed — manual review required"],
            "validation_warnings": [], "attempt_count": 3, "status": "need_review",
            "source_filename": uploaded.name, "source": "upload",
            "content_hash": content_hash,
        })
        if db_result["ok"]:
            upload_document(db_result["data"]["id"], file_bytes, uploaded.name)
        results.append((uploaded.name, "failed", None, [], content_hash))
        continue

    if not invoice.dit_is_invoice:
        st.error(f"This document is not an invoice — rejected by DiT (score={invoice.dit_confidence:.3f}).")
        db_result = save_invoice({
            "vendor_name": "", "invoice_date": "", "invoice_id": "",
            "total_amount": None, "subtotal": None, "tax_amount": None,
            "currency": "MAD", "expense_category": "Other",
            "dit_confidence": invoice.dit_confidence,
            "dit_label": invoice.dit_label or "NON_INVOICE",
            "dit_is_invoice": False,
            "llm_confidence": "", "is_valid": False,
            "validation_errors": [], "validation_warnings": [],
            "attempt_count": 1, "status": "rejected",
            "source_filename": uploaded.name, "source": "upload",
            "content_hash": content_hash,
        })
        if db_result["ok"]:
            upload_document(db_result["data"]["id"], file_bytes, uploaded.name)
        results.append((uploaded.name, "rejected", invoice, [], content_hash))
        continue

    status_val = "validated" if invoice.is_valid else "need_review"
    if status_val == "validated":
        st.success("Invoice validated successfully.")
    else:
        st.warning("Invoice needs manual review — one or more required fields are missing or invalid.")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown("**General Information**")
        st.text(f"Vendor       : {invoice.vendor_name or 'N/A'}")
        st.text(f"Date         : {invoice.invoice_date or 'N/A'}")
        st.text(f"Invoice #    : {invoice.invoice_id or 'N/A'}")
        st.text(f"Category     : {invoice.expense_category or 'N/A'}")
    with col2:
        st.markdown("**Amounts**")
        st.text(f"Subtotal     : {invoice.subtotal or 'N/A'}")
        st.text(f"Tax          : {invoice.tax_amount or 'N/A'}")
        st.text(f"Total        : {invoice.total_amount or 'N/A'}")
        st.text(f"Currency     : {invoice.currency or 'N/A'}")
    with col3:
        st.markdown("**AI Scores**")
        st.text(f"DiT score    : {invoice.dit_confidence:.3f}" if invoice.dit_confidence else "DiT score    : N/A")
        st.text(f"DiT label    : {invoice.dit_label or 'N/A'}")
        st.text(f"LLM confid.  : {invoice.llm_confidence or 'N/A'}")
        st.text(f"Attempts     : {invoice.attempt_count}")

    if invoice.validation_warnings:
        with st.expander(f"{len(invoice.validation_warnings)} warning(s)"):
            for w in invoice.validation_warnings:
                st.warning(w)
    if invoice.validation_errors:
        with st.expander(f"{len(invoice.validation_errors)} error(s)"):
            for e in invoice.validation_errors:
                st.error(e)

    # Save to DB
    invoice_data = {
        # Vendor
        "vendor_name":                 invoice.vendor_name or "",
        "vendor_address":              invoice.vendor_address or "",
        "vendor_address_recipient":    invoice.vendor_address_recipient or "",
        "vendor_tax_id":               invoice.vendor_tax_id or "",
        # Customer
        "customer_name":               invoice.customer_name or "",
        "customer_id":                 invoice.customer_id or "",
        "customer_address":            invoice.customer_address or "",
        "customer_address_recipient":  invoice.customer_address_recipient or "",
        "customer_tax_id":             invoice.customer_tax_id or "",
        # Invoice info
        "invoice_id":                  invoice.invoice_id or "",
        "purchase_order":              invoice.purchase_order or "",
        "kvk_number":                  invoice.kvk_number or "",
        "payment_term":                invoice.payment_term or "",
        # Dates
        "invoice_date":                invoice.invoice_date or "",
        "due_date":                    invoice.due_date or "",
        "service_start_date":          invoice.service_start_date or "",
        "service_end_date":            invoice.service_end_date or "",
        # Amounts
        "subtotal":                    float(invoice.subtotal) if invoice.subtotal is not None else None,
        "total_discount":              float(invoice.total_discount) if invoice.total_discount is not None else None,
        "tax_amount":                  float(invoice.tax_amount) if invoice.tax_amount is not None else None,
        "total_amount":                float(invoice.total_amount) if invoice.total_amount is not None else None,
        "amount_due":                  float(invoice.amount_due) if invoice.amount_due is not None else None,
        "previous_unpaid_balance":     float(invoice.previous_unpaid_balance) if invoice.previous_unpaid_balance is not None else None,
        "currency":                    invoice.currency or "MAD",
        # Addresses
        "billing_address":             invoice.billing_address or "",
        "billing_address_recipient":   invoice.billing_address_recipient or "",
        "shipping_address":            invoice.shipping_address or "",
        "shipping_address_recipient":  invoice.shipping_address_recipient or "",
        "remittance_address":          invoice.remittance_address or "",
        "remittance_address_recipient":invoice.remittance_address_recipient or "",
        "service_address":             invoice.service_address or "",
        "service_address_recipient":   invoice.service_address_recipient or "",
        # Classification
        "expense_category":            invoice.expense_category or "Other",
        # AI pipeline
        "dit_confidence":              invoice.dit_confidence,
        "dit_label":                   invoice.dit_label or "",
        "dit_is_invoice":              invoice.dit_is_invoice,
        "llm_confidence":              invoice.llm_confidence or "",
        "is_valid":                    invoice.is_valid,
        "validation_errors":           invoice.validation_errors or [],
        "validation_warnings":         invoice.validation_warnings or [],
        "attempt_count":               invoice.attempt_count,
        # Metadata
        "status":                      status_val,
        "source_filename":             uploaded.name,
        "source":                      "upload",
        "content_hash":                content_hash,
    }
    db_result = save_invoice(invoice_data)

    if db_result["ok"]:
        invoice_id = db_result["data"].get("id")
        # Store original file for visual review
        upload_document(invoice_id, file_bytes, uploaded.name)

        if exported:
            excel_path = exported[0]
            with open(excel_path, "rb") as f:
                excel_bytes = f.read()
            up = upload_excel(invoice_id, excel_bytes, os.path.basename(excel_path))
            if up["ok"]:
                st.download_button(
                    label=f"Download Excel Report — {uploaded.name}",
                    data=excel_bytes,
                    file_name=os.path.basename(excel_path),
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key=f"dl_{idx}",
                )

    results.append((uploaded.name, status_val, invoice, exported, content_hash))

# Final summary (only if more than one file)
if len(uploaded_files) > 1:
    st.markdown("---")
    st.subheader("Summary")
    validated  = sum(1 for _, s, _, _, _ in results if s == "validated")
    review     = sum(1 for _, s, _, _, _ in results if s == "need_review")
    rejected   = sum(1 for _, s, _, _, _ in results if s == "rejected")
    failed     = sum(1 for _, s, _, _, _ in results if s in ("failed", "error"))
    duplicates = sum(1 for _, s, _, _, _ in results if s == "duplicate")

    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Validated",     validated)
    col2.metric("Need Review",   review)
    col3.metric("Rejected",      rejected)
    col4.metric("Duplicates",    duplicates)
    col5.metric("Errors",        failed)
