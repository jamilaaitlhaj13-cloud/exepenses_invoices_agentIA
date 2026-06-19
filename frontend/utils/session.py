"""
utils/session.py
Persistent session management via browser cookies.
JWT tokens are stored client-side using extra-streamlit-components.
"""
import streamlit as st

# Cookie lifetime: 30 days
COOKIE_EXPIRY_DAYS = 30

_COOKIE_KEYS = {
    "access_token":  "sea_access",
    "refresh_token": "sea_refresh",
    "company_name":  "sea_company",
    "company_id":    "sea_cid",
}


def _get_cookie_manager():
    """Returns the CookieManager (singleton within the Streamlit session)."""
    try:
        import extra_streamlit_components as stx
        # fixed key = single manager for the entire app
        return stx.CookieManager(key="sea_cookie_mgr")
    except Exception:
        return None


def restore_session() -> bool:
    """
    Reads browser cookies and restores the session if tokens exist.
    Returns True if the session was successfully restored.
    """
    # Already authenticated in session state — nothing to do
    if st.session_state.get("access_token"):
        return True

    cm = _get_cookie_manager()
    if cm is None:
        return False

    access  = cm.get(_COOKIE_KEYS["access_token"])
    refresh = cm.get(_COOKIE_KEYS["refresh_token"])

    if not access or not refresh:
        return False

    st.session_state["access_token"]  = access
    st.session_state["refresh_token"] = refresh
    st.session_state["company_name"]  = cm.get(_COOKIE_KEYS["company_name"]) or ""
    raw_cid = cm.get(_COOKIE_KEYS["company_id"])
    try:
        st.session_state["company_id"] = int(raw_cid) if raw_cid else None
    except (ValueError, TypeError):
        st.session_state["company_id"] = None
    return True


def save_session_cookies(data: dict):
    """
    Saves session data to cookies AND to st.session_state.
    Called after a successful login or registration.
    """
    st.session_state["access_token"]  = data.get("access", "")
    st.session_state["refresh_token"] = data.get("refresh", "")
    st.session_state["company_name"]  = data.get("company_name", "")
    st.session_state["company_id"]    = data.get("company_id")

    cm = _get_cookie_manager()
    if cm is None:
        return

    cm.set(_COOKIE_KEYS["access_token"],  data.get("access", ""),
           expires_at=_expiry_date())
    cm.set(_COOKIE_KEYS["refresh_token"], data.get("refresh", ""),
           expires_at=_expiry_date())
    cm.set(_COOKIE_KEYS["company_name"],  data.get("company_name", ""),
           expires_at=_expiry_date())
    cm.set(_COOKIE_KEYS["company_id"],    str(data.get("company_id", "")),
           expires_at=_expiry_date())


def clear_session_cookies():
    """Deletes all session cookies and clears st.session_state."""
    for key in ["access_token", "refresh_token", "company_name", "company_id"]:
        st.session_state.pop(key, None)

    cm = _get_cookie_manager()
    if cm is None:
        return
    for cookie_name in _COOKIE_KEYS.values():
        try:
            cm.delete(cookie_name)
        except Exception:
            pass


def _expiry_date():
    from datetime import datetime, timedelta
    return datetime.now() + timedelta(days=COOKIE_EXPIRY_DAYS)
