"""
Dashboard — Invoice processing overview
"""
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import sys, os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

st.set_page_config(page_title="Dashboard", layout="wide")
st.markdown("<style>[data-testid='stSidebarNav']{display:none}</style>", unsafe_allow_html=True)

from utils.api import is_logged_in, get_stats, logout

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
st.title(" Dashboard")
st.caption("Real-time overview of your invoice processing")

# Load stats
with st.spinner("Loading statistics..."):
    stats = get_stats()

if not stats:
    st.warning("Unable to load statistics. Make sure the Django backend is running.")
    st.stop()

total       = stats.get("total", 0)
validated   = stats.get("validated", 0)
rejected    = stats.get("rejected", 0)
need_review = stats.get("need_review", 0)
total_amt   = stats.get("total_amount", 0.0)

# KPI Cards
col1, col2, col3, col4, col5 = st.columns(5)
col1.metric(" Total Processed", total)
col2.metric(" Validated",        validated,   delta=f"{validated/total*100:.0f}%" if total else None)
col3.metric(" Rejected (DiT)",   rejected)
col4.metric(" Needs Review",     need_review)
col5.metric(" Validated Amount", f"{total_amt:,.2f}")

st.markdown("---")

# Charts
by_category = stats.get("by_category", [])
by_source   = stats.get("by_source", [])

col_chart1, col_chart2 = st.columns([2, 1])

with col_chart1:
    st.subheader(" Invoices by Category")
    if by_category:
        df_cat = pd.DataFrame(by_category)
        df_cat.columns = ["Category", "Count", "Total Amount"]
        df_cat["Total Amount"] = df_cat["Total Amount"].astype(float).fillna(0)
        fig = px.bar(
            df_cat, x="Category", y="Count",
            color="Total Amount", color_continuous_scale="Blues",
            text="Count",
        )
        fig.update_layout(showlegend=False, plot_bgcolor="rgba(0,0,0,0)",
                          paper_bgcolor="rgba(0,0,0,0)", height=300)
        fig.update_traces(textposition="outside")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No category data available yet.")

with col_chart2:
    st.subheader(" Status Breakdown")
    if total > 0:
        labels = ["Validated", "Rejected", "Needs Review"]
        values = [validated, rejected, need_review]
        colors = ["#2ecc71", "#e74c3c", "#f39c12"]
        fig2 = go.Figure(data=[go.Pie(
            labels=labels, values=values,
            marker_colors=colors, hole=0.5,
            textinfo="label+percent",
        )])
        fig2.update_layout(
            showlegend=False, height=300,
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            margin=dict(t=10, b=10, l=10, r=10),
        )
        st.plotly_chart(fig2, use_container_width=True)
    else:
        st.info("No data yet.")

# Amount by category
if by_category:
    st.subheader(" Total Amount by Category")
    df_amt = pd.DataFrame(by_category)
    df_amt.columns = ["Category", "Count", "Amount"]
    df_amt["Amount"] = df_amt["Amount"].astype(float).fillna(0)
    fig3 = px.pie(df_amt, values="Amount", names="Category",
                  color_discrete_sequence=px.colors.qualitative.Set3)
    fig3.update_layout(height=350, paper_bgcolor="rgba(0,0,0,0)")
    st.plotly_chart(fig3, use_container_width=True)

st.markdown("---")

# Recent invoices
st.subheader(" Recent Invoices")
recent = stats.get("recent", [])
if recent:
    df_recent = pd.DataFrame(recent)
    cols_display = ["vendor_name", "invoice_date", "total_amount",
                    "currency", "expense_category", "status", "source"]
    cols_labels = {
        "vendor_name":      "Vendor",
        "invoice_date":     "Date",
        "total_amount":     "Amount",
        "currency":         "Currency",
        "expense_category": "Category",
        "status":           "Status",
        "source":           "Source",
    }
    df_display = df_recent[[c for c in cols_display if c in df_recent.columns]]
    df_display = df_display.rename(columns=cols_labels)

    status_icons = {"validated": "✅", "rejected": "❌", "need_review": "🔍", "processing": "⏳"}
    if "Status" in df_display.columns:
        df_display["Status"] = df_display["Status"].map(lambda s: f"{status_icons.get(s, '')} {s}")

    st.dataframe(df_display, use_container_width=True, hide_index=True)
else:
    st.info("No invoices processed yet. Use **Upload Invoice** or **Run Pipeline** to get started!")
