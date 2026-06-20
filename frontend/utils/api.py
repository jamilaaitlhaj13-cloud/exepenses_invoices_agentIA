"""
Client HTTP centralisé pour appeler l'API Django.
Toutes les pages Streamlit importent ce module.
"""
import requests
import streamlit as st

BASE_URL = "http://localhost:8000/api"


def _headers():
    token = st.session_state.get("access_token", "")
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _headers_no_ct():
    """Headers sans Content-Type pour les uploads multipart."""
    token = st.session_state.get("access_token", "")
    return {"Authorization": f"Bearer {token}"}


# ── AUTH ──────────────────────────────────────────────────────────────────────

def _safe_json(r) -> dict:
    try:
        return r.json()
    except Exception:
        return {"error": f"Server error ({r.status_code}): {r.text[:300] or 'empty response'}"}


def register(data: dict) -> dict:
    r = requests.post(f"{BASE_URL}/auth/register/", json=data, timeout=15)
    return {"ok": r.ok, "data": _safe_json(r)}


def login(email: str, password: str) -> dict:
    r = requests.post(
        f"{BASE_URL}/auth/login/",
        json={"email": email, "password": password},
        timeout=15,
    )
    return {"ok": r.ok, "data": _safe_json(r)}


def refresh_token() -> bool:
    refresh = st.session_state.get("refresh_token", "")
    if not refresh:
        return False
    r = requests.post(
        f"{BASE_URL}/auth/refresh/",
        json={"refresh": refresh},
        timeout=10,
    )
    if r.ok:
        st.session_state["access_token"] = r.json()["access"]
        return True
    return False


def get_profile() -> dict:
    r = requests.get(f"{BASE_URL}/auth/profile/", headers=_headers(), timeout=10)
    return r.json() if r.ok else {}


# ── DASHBOARD ─────────────────────────────────────────────────────────────────

def get_stats() -> dict:
    r = requests.get(f"{BASE_URL}/invoices/stats/", headers=_headers(), timeout=15)
    return r.json() if r.ok else {}


def get_dit_scores() -> list:
    r = requests.get(f"{BASE_URL}/invoices/dit_scores/", headers=_headers(), timeout=15)
    return r.json() if r.ok else []


def get_timeline() -> list:
    r = requests.get(f"{BASE_URL}/invoices/timeline/", headers=_headers(), timeout=15)
    return r.json() if r.ok else []


def get_metrics() -> dict:
    r = requests.get(f"{BASE_URL}/invoices/metrics/", headers=_headers(), timeout=15)
    return r.json() if r.ok else {}


# ── INVOICES ──────────────────────────────────────────────────────────────────

def list_invoices(status=None, category=None, source=None) -> list:
    params = {}
    if status:
        params["status"] = status
    if category:
        params["category"] = category
    if source:
        params["source"] = source
    r = requests.get(
        f"{BASE_URL}/invoices/",
        headers=_headers(),
        params=params,
        timeout=15,
    )
    return r.json() if r.ok else []


def check_invoice_hash(content_hash: str) -> bool:
    """Returns True if an invoice with this MD5 hash has already been processed."""
    try:
        r = requests.get(
            f"{BASE_URL}/invoices/check_hash/",
            headers=_headers(),
            params={"hash": content_hash},
            timeout=10,
        )
        return r.ok and r.json().get("exists", False)
    except Exception:
        return False


def save_invoice(invoice_data: dict) -> dict:
    r = requests.post(
        f"{BASE_URL}/invoices/",
        json=invoice_data,
        headers=_headers(),
        timeout=15,
    )
    try:
        data = r.json()
    except Exception:
        data = {"detail": r.text[:300] or "Empty server response"}
    return {"ok": r.ok, "data": data}


def upload_excel(invoice_id: int, excel_bytes: bytes, filename: str) -> dict:
    files = {"excel_file": (filename, excel_bytes,
             "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    r = requests.post(
        f"{BASE_URL}/invoices/{invoice_id}/upload_excel/",
        headers=_headers_no_ct(),
        files=files,
        timeout=20,
    )
    try:
        data = r.json()
    except Exception:
        data = {"detail": r.text[:300] or "Empty response"}
    return {"ok": r.ok, "data": data}


def upload_document(invoice_id: int, file_bytes: bytes, filename: str) -> dict:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "pdf"
    mime = {"pdf": "application/pdf", "png": "image/png",
            "jpg": "image/jpeg", "jpeg": "image/jpeg"}.get(ext, "application/octet-stream")
    r = requests.post(
        f"{BASE_URL}/invoices/{invoice_id}/upload_document/",
        headers=_headers_no_ct(),
        files={"document": (filename, file_bytes, mime)},
        timeout=30,
    )
    return {"ok": r.ok, "data": r.json() if r.ok else {}}


def get_document_url(invoice_id: int) -> str:
    return f"{BASE_URL}/invoices/{invoice_id}/document/"


def get_to_review() -> list:
    r = requests.get(f"{BASE_URL}/invoices/to_review/", headers=_headers(), timeout=15)
    return r.json() if r.ok else []


def download_excel(invoice_id: int) -> bytes | None:
    r = requests.get(
        f"{BASE_URL}/invoices/{invoice_id}/excel/",
        headers=_headers(),
        timeout=30,
    )
    return r.content if r.ok else None


def delete_invoice(invoice_id: int) -> bool:
    r = requests.delete(
        f"{BASE_URL}/invoices/{invoice_id}/",
        headers=_headers(),
        timeout=10,
    )
    return r.status_code == 204


# ── SESSION HELPERS ───────────────────────────────────────────────────────────

def is_logged_in() -> bool:
    return bool(st.session_state.get("access_token"))


def logout():
    from utils.session import clear_session_cookies
    clear_session_cookies()


def save_session(data: dict):
    from utils.session import save_session_cookies
    save_session_cookies(data)
