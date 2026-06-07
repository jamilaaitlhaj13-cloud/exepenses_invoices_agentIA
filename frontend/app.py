"""
Landing page — Sign In / Create Account
"""
import streamlit as st
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

st.set_page_config(
    page_title="SmartExpenseAgent",
    layout="centered",
    initial_sidebar_state="collapsed",
)

from utils.api import is_logged_in, login, register, save_session

# Redirect if already logged in
if is_logged_in():
    st.switch_page("pages/1_Dashboard.py")

# CSS
st.markdown("""
<style>
  [data-testid="stSidebar"] { display: none; }
  [data-testid="stSidebarNav"] { display: none; }
  .hero { text-align: center; padding: 2rem 0 1.5rem; }
  .hero h1 { font-size: 2.8rem; font-weight: 800; color: #1a1a2e; margin: 0; }
  .hero p  { font-size: 1.1rem; color: #555; margin-top: 0.5rem; }
  .badge   { display: inline-block; background: #e8f4fd; color: #0066cc;
             padding: 4px 12px; border-radius: 20px; font-size: 0.85rem;
             margin: 0.3rem; }
  .divider { border: none; border-top: 1px solid #e0e0e0; margin: 1.5rem 0; }
</style>
""", unsafe_allow_html=True)

# Hero section
st.markdown("""
<div class="hero">
  <h1>SmartExpenseAgent</h1>
  <p>Automated invoice processing powered by Artificial Intelligence</p>
  <div>
    <span class="badge">DiT Vision</span>
    <span class="badge">Azure OCR</span>
    <span class="badge">LLM Classification</span>
    <span class="badge">Excel Export</span>
  </div>
</div>
<hr class="divider">
""", unsafe_allow_html=True)

# Tabs
tab_login, tab_register = st.tabs(["Sign In", " Create Account"])

# SIGN IN
with tab_login:
    st.markdown("#### Welcome back!")
    with st.form("form_login"):
        email    = st.text_input("Business email", placeholder="contact@your-company.com")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Sign In", use_container_width=True, type="primary")

    if submitted:
        if not email or not password:
            st.error("Please fill in all fields.")
        else:
            with st.spinner("Signing in..."):
                result = login(email.strip().lower(), password)
            if result["ok"]:
                save_session(result["data"])
                st.success(f"Welcome, **{result['data']['company_name']}**!")
                st.switch_page("pages/1_Dashboard.py")
            else:
                err = result["data"].get("error", "Invalid credentials.")
                st.error(err)

# CREATE ACCOUNT
with tab_register:
    st.markdown("#### Create your company account")

    INDUSTRIES = {
        "tech":          "Technology / IT",
        "finance":       "Finance & Banking",
        "healthcare":    "Healthcare",
        "retail":        "Retail & Distribution",
        "manufacturing": "Manufacturing",
        "consulting":    "Consulting & Services",
        "education":     "Education",
        "real_estate":   "Real Estate",
        "transport":     "Transport & Logistics",
        "other":         "Other",
    }

    with st.form("form_register"):
        col1, col2 = st.columns(2)
        with col1:
            company_name = st.text_input("Company name *", placeholder="ACME Corp Ltd")
            email_r      = st.text_input("Business email *", placeholder="admin@acme.com")
            country      = st.text_input("Country *", value="Morocco")
            rc_number    = st.text_input("Registration number", placeholder="RC 123456")
        with col2:
            industry     = st.selectbox("Industry *", options=list(INDUSTRIES.keys()),
                                        format_func=lambda k: INDUSTRIES[k])
            phone        = st.text_input("Phone", placeholder="+1 555 000 0000")
            city         = st.text_input("City", placeholder="New York")

        st.markdown("---")
        col3, col4 = st.columns(2)
        with col3:
            password_r  = st.text_input("Password *", type="password",
                                         help="Minimum 8 characters")
        with col4:
            password2_r = st.text_input("Confirm password *", type="password")

        submitted_r = st.form_submit_button("Create Account", use_container_width=True, type="primary")

    if submitted_r:
        if not all([company_name, email_r, country, password_r, password2_r]):
            st.error("Please fill in all required fields (*)")
        elif password_r != password2_r:
            st.error("Passwords do not match.")
        elif len(password_r) < 8:
            st.error("Password must be at least 8 characters.")
        else:
            payload = {
                "company_name": company_name.strip(),
                "email":        email_r.strip().lower(),
                "industry":     industry,
                "phone":        phone.strip(),
                "country":      country.strip(),
                "city":         city.strip(),
                "rc_number":    rc_number.strip(),
                "password":     password_r,
                "password2":    password2_r,
            }
            with st.spinner("Creating account..."):
                result = register(payload)

            if result["ok"]:
                save_session(result["data"])
                st.success("Account created successfully! Redirecting...")
                st.switch_page("pages/1_Dashboard.py")
            else:
                for field, errors in result["data"].items():
                    if isinstance(errors, list):
                        for e in errors:
                            st.error(f"**{field}**: {e}")
                    else:
                        st.error(f"**{field}**: {errors}")

# Footer
st.markdown("---")
st.markdown(
    "<p style='text-align:center; color:#aaa; font-size:0.8rem;'>"
    "SmartExpenseAgent — Powered by DiT + Azure AI + LangChain"
    "</p>",
    unsafe_allow_html=True,
)
