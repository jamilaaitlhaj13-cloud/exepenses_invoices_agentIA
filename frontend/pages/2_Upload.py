"""
Page 2 — Direct invoice upload
"""
import streamlit as st
import tempfile, os, sys, time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

st.set_page_config(page_title="Upload Invoice", layout="wide")
st.markdown("<style>[data-testid='stSidebarNav']{display:none}</style>", unsafe_allow_html=True)

from utils.api import is_logged_in, save_invoice, upload_excel, logout

if not is_logged_in():
    st.switch_page("app.py")

# Sidebar
with st.sidebar:
    st.markdown(f"###  {st.session_state.get('company_name', '')}")
    st.markdown("---")
    st.page_link("pages/1_Dashboard.py",      label=" Dashboard")
    st.page_link("pages/2_Upload.py",          label=" Upload Invoice")
    st.page_link("pages/3_Pipeline.py",        label=" Run Pipeline")
    st.page_link("pages/4_Telechargements.py", label=" Downloads")
    st.markdown("---")
    if st.button(" Sign Out", use_container_width=True):
        logout()
        st.switch_page("app.py")

# Header
st.title("Upload Invoice")
st.caption("Upload a PDF or image file — the agent processes it immediately")

# File uploader
uploaded = st.file_uploader(
    "Drag and drop your invoice here",
    type=["pdf", "jpg", "jpeg", "png"],
    help="Accepted formats: PDF, JPG, JPEG, PNG — max 10 MB",
)

if not uploaded:
    st.markdown("""
    <div style="background:#f8f9fa; border-radius:12px; padding:2rem; text-align:center; color:#666; margin-top:2rem;">
      <h3> How does it work?</h3>
      <div style="display:grid; grid-template-columns:1fr 1fr 1fr 1fr; gap:1rem; margin-top:1rem;">
        <div><b>1. DiT Vision</b><br>Visually verifies the document is an invoice</div>
        <div><b>2. Azure OCR</b><br>Extracts all fields (vendor, amount, date...)</div>
        <div><b>3. LLM</b><br>Classifies the expense and reformats data</div>
        <div><b>4. Validation</b><br>Applies 12 business rules and generates Excel report</div>
      </div>
    </div>
    """, unsafe_allow_html=True)
    st.stop()

# Process
st.markdown("---")
st.subheader(f" Selected file: `{uploaded.name}`")
st.markdown(f"Size: `{uploaded.size / 1024:.1f} KB`")

if st.button(" Process Invoice", type="primary", use_container_width=True):

    suffix = Path(uploaded.name).suffix.lower()
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(uploaded.read())
        tmp_path = Path(tmp.name)

    steps = [
        (" Visual verification (DiT)...",     "Document Image Transformer"),
        (" OCR extraction (Azure)...",         "Azure Document Intelligence"),
        (" LLM classification...",             "Azure OpenAI GPT"),
        (" Business rules validation...",       "12 validation rules"),
        (" Generating Excel report...",         "Excel export"),
    ]

    progress_bar = st.progress(0)
    status_text  = st.empty()

    try:
        agent_root = Path(__file__).resolve().parent.parent.parent
        sys.path.insert(0, str(agent_root))

        from agent.smart_expense_agent import SmartExpenseAgent
        agent = SmartExpenseAgent()

        for i, (msg, detail) in enumerate(steps[:-1]):
            status_text.markdown(f"**{msg}** *({detail})*")
            progress_bar.progress((i + 1) * 20)
            time.sleep(0.3)

        status_text.markdown("**⚙️ Processing...**")
        invoice = agent._process(tmp_path)

        progress_bar.progress(80)
        status_text.markdown("** Generating Excel report...**")

        if invoice:
            exported = agent.exporter.export([invoice])
            agent.dataset_builder.add_invoice(invoice)

        progress_bar.progress(100)
        status_text.markdown("** Processing complete!**")
        time.sleep(0.5)
        status_text.empty()

    except ImportError:
        st.warning(" Agent not available in this context. Demo mode.")
        invoice  = None
        exported = []
        for i, (msg, detail) in enumerate(steps):
            status_text.markdown(f"**{msg}**")
            progress_bar.progress((i + 1) * 20)
            time.sleep(0.6)
        status_text.empty()
    finally:
        tmp_path.unlink(missing_ok=True)

    # Display results
    st.markdown("---")

    if invoice:
        status_val = "validated" if invoice.is_valid else "need_review"
        if not invoice.dit_is_invoice:
            status_val = "rejected"

        if status_val == "validated":
            st.success(" Invoice validated successfully!")
        elif status_val == "rejected":
            st.error(" Document rejected — not an invoice (DiT)")
        else:
            st.warning("🔍 Invoice needs manual review")

        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown("** General Information**")
            st.text(f"Vendor       : {invoice.vendor_name or 'N/A'}")
            st.text(f"Date         : {invoice.invoice_date or 'N/A'}")
            st.text(f"Invoice #    : {invoice.invoice_id or 'N/A'}")
            st.text(f"Category     : {invoice.expense_category or 'N/A'}")
        with col2:
            st.markdown("** Amounts**")
            st.text(f"Subtotal     : {invoice.subtotal or 'N/A'}")
            st.text(f"Tax          : {invoice.tax_amount or 'N/A'}")
            st.text(f"Total        : {invoice.total_amount or 'N/A'}")
            st.text(f"Currency     : {invoice.currency or 'N/A'}")
        with col3:
            st.markdown("** AI Scores**")
            dit_score = f"{invoice.dit_confidence:.3f}" if invoice.dit_confidence else "N/A"
            st.text(f"DiT score    : {dit_score}")
            st.text(f"DiT label    : {invoice.dit_label or 'N/A'}")
            st.text(f"LLM confid.  : {invoice.llm_confidence or 'N/A'}")
            st.text(f"Attempts     : {invoice.attempt_count}")

        if invoice.validation_warnings:
            with st.expander(f" {len(invoice.validation_warnings)} warning(s)"):
                for w in invoice.validation_warnings:
                    st.warning(w)
        if invoice.validation_errors:
            with st.expander(f" {len(invoice.validation_errors)} error(s)"):
                for e in invoice.validation_errors:
                    st.error(e)

        # Save to Django
        invoice_data = {
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
            "source_filename":     uploaded.name,
            "source":              "upload",
        }
        result = save_invoice(invoice_data)
        if not result["ok"]:
            st.warning(f" Invoice processed but not saved to database: {result['data']}")
        if result["ok"]:
            invoice_id = result["data"].get("id")
            st.session_state["last_invoice_id"] = invoice_id

            if exported:
                excel_path = exported[0]
                with open(excel_path, "rb") as f:
                    excel_bytes = f.read()
                up = upload_excel(invoice_id, excel_bytes, os.path.basename(excel_path))
                if up["ok"]:
                    st.markdown("---")
                    st.success(" Excel report generated!")
                    st.download_button(
                        label=" Download Excel Report",
                        data=excel_bytes,
                        file_name=os.path.basename(excel_path),
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True,
                    )
    else:
        st.error(" Invoice could not be processed. Check the **Downloads** section for manual review.")
