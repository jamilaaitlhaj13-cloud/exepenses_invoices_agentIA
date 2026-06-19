"""
Page 5 — Révision visuelle des documents rejetés et en attente
Permet de vérifier manuellement les documents rejetés par DiT ou en need_review.
"""
import streamlit as st
import sys, os
import requests
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

st.set_page_config(page_title="Document Review", layout="wide")
st.markdown("<style>[data-testid='stSidebarNav']{display:none}</style>", unsafe_allow_html=True)

from utils.api import is_logged_in, get_to_review, get_document_url, logout
from utils.session import restore_session

restore_session()
if not is_logged_in():
    st.switch_page("app.py")

BASE_URL = "http://localhost:8000/api"

def _auth_headers():
    token = st.session_state.get("access_token", "")
    return {"Authorization": f"Bearer {token}"}

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
st.title("Document Review")
st.caption("Visually inspect rejected and flagged documents — identify misclassified invoices for reprocessing.")

# Filters
col_f1, col_f2, col_f3 = st.columns([2, 2, 1])
with col_f1:
    filter_status = st.selectbox(
        "Filter by status",
        ["All", "Rejected (DiT)", "Needs Review"],
        index=0,
    )
with col_f2:
    filter_source = st.selectbox("Filter by source", ["All", "upload", "email"], index=0)
with col_f3:
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("Refresh", use_container_width=True):
        st.rerun()

# Load documents
with st.spinner("Loading documents..."):
    documents = get_to_review()

if not documents:
    st.info("No documents to review. All processed invoices have been validated.")
    st.stop()

# Apply filters
if filter_status == "Rejected (DiT)":
    documents = [d for d in documents if d.get("status") == "rejected"]
elif filter_status == "Needs Review":
    documents = [d for d in documents if d.get("status") == "need_review"]

if filter_source != "All":
    documents = [d for d in documents if d.get("source") == filter_source]

PAGE_SIZE = 10
if "review_page" not in st.session_state:
    st.session_state.review_page = 1

# Reset page when filters change
filter_key = f"{filter_status}_{filter_source}"
if st.session_state.get("_review_filter_key") != filter_key:
    st.session_state.review_page = 1
    st.session_state["_review_filter_key"] = filter_key

total_docs   = len(documents)
current_page = st.session_state.review_page
documents    = documents[: current_page * PAGE_SIZE]

STATUS_COLOR = {
    "rejected":    "#e74c3c",
    "need_review": "#f39c12",
}
STATUS_LABEL = {
    "rejected":    "Rejected by DiT",
    "need_review": "Needs Review",
}

st.markdown(f"**{len(documents)} document(s) found**")
st.markdown("---")

for doc in documents:
    doc_id     = doc.get("id")
    filename   = doc.get("source_filename") or f"Document #{doc_id}"
    status     = doc.get("status", "")
    dit_score  = doc.get("dit_confidence")
    dit_label  = doc.get("dit_label", "")
    source     = doc.get("source", "")
    errors     = doc.get("validation_errors") or []
    created_at = doc.get("created_at", "")[:10] if doc.get("created_at") else ""
    color      = STATUS_COLOR.get(status, "#aaa")
    label      = STATUS_LABEL.get(status, status)

    with st.expander(
        f"**{filename}** — {label} — {created_at}",
        expanded=False,
    ):
        col_info, col_doc = st.columns([1, 2])

        with col_info:
            st.markdown(f"""
            <div style="border-left: 4px solid {color}; padding: 0.8rem 1rem; border-radius: 6px; background: rgba(255,255,255,0.03);">
                <b>Status</b>: <span style="color:{color}">{label}</span><br>
                <b>File</b>: {filename}<br>
                <b>Source</b>: {source}<br>
                <b>Date</b>: {created_at}<br>
                {"<b>DiT Score</b>: " + f"{dit_score:.4f}" + "<br>" if dit_score is not None else ""}
                {"<b>DiT Label</b>: " + dit_label + "<br>" if dit_label else ""}
            </div>
            """, unsafe_allow_html=True)

            if errors:
                st.markdown("**Errors:**")
                for e in errors:
                    st.error(e)

            st.markdown("")

            # Bouton télécharger le document original
            try:
                r = requests.get(
                    f"{BASE_URL}/invoices/{doc_id}/document/",
                    headers=_auth_headers(),
                    timeout=15,
                )
                if r.ok:
                    ext  = filename.rsplit(".", 1)[-1].lower() if "." in filename else "pdf"
                    mime = {"pdf": "application/pdf", "png": "image/png",
                            "jpg": "image/jpeg", "jpeg": "image/jpeg"}.get(ext, "application/octet-stream")
                    st.download_button(
                        label="Download original file",
                        data=r.content,
                        file_name=filename,
                        mime=mime,
                        key=f"dl_doc_{doc_id}",
                        use_container_width=True,
                    )
                    doc_bytes = r.content
                    doc_available = True
                else:
                    st.caption("Original file not available.")
                    doc_bytes = None
                    doc_available = False
            except Exception:
                st.caption("Original file not available.")
                doc_bytes = None
                doc_available = False

        with col_doc:
            if doc_available and doc_bytes:
                ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
                if ext == "pdf":
                    # Affiche le PDF inline via un iframe base64
                    import base64
                    b64 = base64.b64encode(doc_bytes).decode()
                    st.markdown(
                        f'<iframe src="data:application/pdf;base64,{b64}" '
                        f'width="100%" height="600px" style="border:none; border-radius:8px;"></iframe>',
                        unsafe_allow_html=True,
                    )
                elif ext in ("jpg", "jpeg", "png"):
                    st.image(doc_bytes, width="stretch")
                else:
                    st.info("Preview not available for this file type.")
            else:
                st.markdown("""
                <div style="height:200px; display:flex; align-items:center; justify-content:center;
                     border: 2px dashed #444; border-radius:8px; color:#666;">
                    No preview — file not stored.<br>
                    Only new documents processed after this feature was enabled will have a preview.
                </div>
                """, unsafe_allow_html=True)

    st.markdown("")

# Bouton "Voir plus"
if current_page * PAGE_SIZE < total_docs:
    remaining = total_docs - current_page * PAGE_SIZE
    st.markdown("---")
    col_more, col_info = st.columns([1, 3])
    with col_more:
        if st.button(f"Show more ({remaining} remaining)", use_container_width=True):
            st.session_state.review_page += 1
            st.rerun()
    with col_info:
        st.caption(f"Showing {min(current_page * PAGE_SIZE, total_docs)} of {total_docs} documents")
