"""
Page 4 — Downloads — Excel reports per invoice and per category
"""
import streamlit as st
import pandas as pd
import sys, os
from pathlib import Path
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

st.set_page_config(page_title="Downloads", layout="wide")
st.markdown("<style>[data-testid='stSidebarNav']{display:none}</style>", unsafe_allow_html=True)

from utils.api import is_logged_in, list_invoices, download_excel, delete_invoice, logout
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
st.title("Downloads")
st.caption("View and download Excel reports for your processed invoices")

# Filters
st.markdown("### Filters")
fcol1, fcol2, fcol3 = st.columns(3)

with fcol1:
    filter_status = st.selectbox(
        "Status",
        options=["All", "validated", "rejected", "need_review"],
        format_func=lambda s: {
            "All":         "All statuses",
            "validated":   "Validated",
            "rejected":    "Rejected",
            "need_review": "Needs Review",
        }.get(s, s),
    )
with fcol2:
    filter_category = st.selectbox(
        "Category",
        options=["All", "SaaS", "Travel", "Office", "Utilities",
                 "IT Hardware", "Consulting & Services",
                 "Marketing & Communication", "Legal & Compliance",
                 "Maintenance & Repair", "Other"],
    )
with fcol3:
    filter_source = st.selectbox(
        "Source",
        options=["All", "email", "upload"],
        format_func=lambda s: {
            "All":    "All sources",
            "email":  "Email pipeline",
            "upload": "Manual upload",
        }.get(s, s),
    )

# Load data
with st.spinner("Loading invoices..."):
    invoices = list_invoices(
        status=None if filter_status == "All" else filter_status,
        category=None if filter_category == "All" else filter_category,
        source=None if filter_source == "All" else filter_source,
    )

st.markdown("---")

if not invoices:
    st.info("No invoices found with these filters.")
    st.stop()

total_shown = len(invoices)
with_excel  = sum(1 for inv in invoices if inv.get("excel_file"))
st.markdown(f"**{total_shown}** invoice(s) found — **{with_excel}** with Excel report")
st.markdown("---")

PAGE_SIZE = 10
if "dl_page" not in st.session_state:
    st.session_state.dl_page = 1

filter_key = f"{filter_status}_{filter_category}_{filter_source}"
if st.session_state.get("_dl_filter_key") != filter_key:
    st.session_state.dl_page = 1
    st.session_state["_dl_filter_key"] = filter_key

visible_invoices = invoices[: st.session_state.dl_page * PAGE_SIZE]

STATUS_LABEL = {
    "validated":   "Validated",
    "rejected":    "Rejected",
    "need_review": "Needs Review",
    "processing":  "Processing",
}

for inv in visible_invoices:
    inv_id     = inv.get("id")
    vendor     = inv.get("vendor_name") or "Unknown vendor"
    date       = inv.get("invoice_date") or "-"
    amount     = inv.get("total_amount")
    currency   = inv.get("currency") or "MAD"
    category   = inv.get("expense_category") or "-"
    status_raw = inv.get("status", "")
    source     = inv.get("source", "-")
    filename   = inv.get("source_filename") or "-"
    has_excel  = bool(inv.get("excel_file"))
    created    = inv.get("created_at", "")[:10] if inv.get("created_at") else "-"

    status_label = STATUS_LABEL.get(status_raw, status_raw)
    amount_str   = f"{float(amount):,.2f} {currency}" if amount else "-"

    with st.expander(f"{status_label} — {vendor} | {date} | {amount_str} | {category}"):
        dcol1, dcol2, dcol3 = st.columns(3)
        with dcol1:
            st.markdown(f"**Vendor:** {vendor}")
            st.markdown(f"**Date:** {date}")
            st.markdown(f"**Invoice #:** {inv.get('invoice_id') or '-'}")
        with dcol2:
            st.markdown(f"**Amount:** {amount_str}")
            st.markdown(f"**Category:** {category}")
            st.markdown(f"**Source:** {'Email' if source == 'email' else 'Upload'}")
        with dcol3:
            st.markdown(f"**Original file:** `{filename}`")
            st.markdown(f"**Processed on:** {created}")
            dit = inv.get("dit_confidence")
            st.markdown(f"**DiT score:** {float(dit):.3f}" if dit else "**DiT score:** -")

        if has_excel:
            if st.button("Download Excel Report", key=f"dl_{inv_id}"):
                with st.spinner("Downloading..."):
                    excel_bytes = download_excel(inv_id)
                if excel_bytes:
                    st.download_button(
                        label="Save file",
                        data=excel_bytes,
                        file_name=f"invoice_{vendor}_{date}.xlsx".replace(" ", "_"),
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        key=f"save_{inv_id}",
                    )
                else:
                    st.error("Unable to download the file.")
        else:
            st.caption("No Excel report available for this invoice.")

if st.session_state.dl_page * PAGE_SIZE < total_shown:
    remaining = total_shown - st.session_state.dl_page * PAGE_SIZE
    st.markdown("---")
    col_more, col_info = st.columns([1, 3])
    with col_more:
        if st.button(f"Show more ({remaining} remaining)", use_container_width=True):
            st.session_state.dl_page += 1
            st.rerun()
    with col_info:
        st.caption(f"Showing {min(st.session_state.dl_page * PAGE_SIZE, total_shown)} of {total_shown} invoices")

st.markdown("---")

st.markdown("### Export by Category")
st.caption(
    "Complete Excel files generated by the agent — contain all fields extracted by "
    "Azure Document Intelligence (vendor, customer, amounts, line items, IBAN, addresses, service dates...)"
)

_agent_root  = Path(__file__).resolve().parent.parent.parent
_outputs_dir = _agent_root / "data" / "outputs"

CATEGORY_LABELS = {
    "SaaS":                    "SaaS",
    "Travel":                  "Travel",
    "Office":                  "Office",
    "Utilities":               "Utilities",
    "IT_Hardware":             "IT Hardware",
    "Consulting_Services":     "Consulting & Services",
    "Marketing_Communication": "Marketing & Communication",
    "Legal_Compliance":        "Legal & Compliance",
    "Maintenance_Repair":      "Maintenance & Repair",
    "Other":                   "Other",
}

if _outputs_dir.exists():
    excel_files = sorted(_outputs_dir.glob("*.xlsx"))
    if excel_files:
        cols = st.columns(min(len(excel_files), 3))
        for i, excel_path in enumerate(excel_files):
            stem  = excel_path.stem
            label = CATEGORY_LABELS.get(stem, stem.replace("_", " "))
            try:
                df_check = pd.read_excel(excel_path, sheet_name="Invoices")
                nb = len(df_check)
            except Exception:
                nb = 0

            with cols[i % 3]:
                with open(excel_path, "rb") as f:
                    st.download_button(
                        label=f"{label} ({nb} invoice(s))",
                        data=f.read(),
                        file_name=excel_path.name,
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        key=f"cat_excel_{stem}",
                        use_container_width=True,
                    )
    else:
        st.info("No category Excel files found. Run the pipeline to generate them.")
else:
    st.warning(f"Outputs folder not found: `{_outputs_dir}`")
