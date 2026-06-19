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

from utils.api import is_logged_in, get_stats, get_dit_scores, get_timeline, logout
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
    st.markdown("---")
    if st.button("Sign Out", use_container_width=True):
        logout()
        st.switch_page("app.py")

# Header
col_title, col_refresh = st.columns([5, 1])
with col_title:
    st.title("Dashboard")
    st.caption("Real-time overview of your invoice processing")
with col_refresh:
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("Refresh", use_container_width=True):
        st.rerun()

# Load data
with st.spinner("Loading statistics..."):
    stats      = get_stats()
    dit_scores = get_dit_scores()
    timeline   = get_timeline()

if not stats:
    st.warning("Unable to load statistics. Make sure the FastAPI backend is running on port 8000.")
    st.stop()

total       = stats.get("total", 0)
validated   = stats.get("validated", 0)
rejected    = stats.get("rejected", 0)
need_review = stats.get("need_review", 0)
total_amt   = stats.get("total_amount", 0.0)
by_category = stats.get("by_category", [])
recent      = stats.get("recent", [])

# ── KPI Cards ─────────────────────────────────────────────────────────────────
# System Handling Rate = factures validées / total traité
system_handling_rate = round(validated / total * 100, 1) if total else 0.0

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Total Processed",      total)
col2.metric("Validated",            validated)
col3.metric("Rejected (DiT)",       rejected)
col4.metric("Needs Review",         need_review)
col5.metric("Validated Amount",     f"{total_amt:,.2f} MAD")

# Bandeau System Handling Rate — recalculé automatiquement à chaque refresh
_color = "#2ecc71" if system_handling_rate >= 80 else "#f39c12" if system_handling_rate >= 50 else "#e74c3c"
st.markdown(
    f"""<div style="background:#f0f4ff; border-left:4px solid {_color};
              padding:0.75rem 1.2rem; border-radius:6px; margin-bottom:0.5rem;">
        <span style="font-size:1.05rem; font-weight:700; color:{_color};">
            System Handling Rate: {system_handling_rate}%
        </span>
        &nbsp;—&nbsp;
        <span style="color:#555;">{validated}/{total} invoices validated</span>
        <span style="font-size:0.8rem; color:#999; margin-left:1rem;">
            (validated / total processed)
        </span>
    </div>""",
    unsafe_allow_html=True,
)

st.markdown("---")

# ── 1. AI Pipeline Card ───────────────────────────────────────────────────────
st.subheader("AI Processing Pipeline")
st.caption("Each document goes through 4 automated stages before being validated.")

p1, p2, p3, p4 = st.columns(4)

with p1:
    st.markdown("""
    <div style="background:#1a1a2e;border-radius:10px;padding:1.2rem;text-align:center;border-left:4px solid #3498db">
        <div style="font-size:1.6rem">DiT Vision</div>
        <div style="color:#3498db;font-size:0.85rem;margin-top:0.3rem">Document Image Transformer</div>
        <div style="margin-top:0.8rem;font-size:1.4rem;font-weight:bold">{}</div>
        <div style="color:#aaa;font-size:0.8rem">documents verified</div>
    </div>
    """.format(total), unsafe_allow_html=True)

with p2:
    accepted = validated + need_review
    st.markdown("""
    <div style="background:#1a1a2e;border-radius:10px;padding:1.2rem;text-align:center;border-left:4px solid #9b59b6">
        <div style="font-size:1.6rem">Azure OCR</div>
        <div style="color:#9b59b6;font-size:0.85rem;margin-top:0.3rem">Document Intelligence</div>
        <div style="margin-top:0.8rem;font-size:1.4rem;font-weight:bold">{}</div>
        <div style="color:#aaa;font-size:0.8rem">fields extracted</div>
    </div>
    """.format(accepted), unsafe_allow_html=True)

with p3:
    st.markdown("""
    <div style="background:#1a1a2e;border-radius:10px;padding:1.2rem;text-align:center;border-left:4px solid #e67e22">
        <div style="font-size:1.6rem">LLM</div>
        <div style="color:#e67e22;font-size:0.85rem;margin-top:0.3rem">Azure OpenAI GPT</div>
        <div style="margin-top:0.8rem;font-size:1.4rem;font-weight:bold">{}</div>
        <div style="color:#aaa;font-size:0.8rem">invoices classified</div>
    </div>
    """.format(accepted), unsafe_allow_html=True)

with p4:
    st.markdown("""
    <div style="background:#1a1a2e;border-radius:10px;padding:1.2rem;text-align:center;border-left:4px solid #2ecc71">
        <div style="font-size:1.6rem">Validation</div>
        <div style="color:#2ecc71;font-size:0.85rem;margin-top:0.3rem">12 Business Rules</div>
        <div style="margin-top:0.8rem;font-size:1.4rem;font-weight:bold">{}</div>
        <div style="color:#aaa;font-size:0.8rem">invoices validated</div>
    </div>
    """.format(validated), unsafe_allow_html=True)

st.markdown("---")

# ── 2. DiT Score Distribution + Timeline ─────────────────────────────────────
col_dit, col_time = st.columns(2)

with col_dit:
    st.subheader("DiT Confidence Score Distribution")
    st.caption("Score close to 1 = invoice confirmed. Score close to 0 = not an invoice. A clear separation shows the model works well.")

    if dit_scores:
        df_dit = pd.DataFrame(dit_scores)
        color_map = {
            "validated":   "#2ecc71",
            "need_review": "#f39c12",
            "rejected":    "#e74c3c",
        }
        fig_dit = px.histogram(
            df_dit, x="score", color="status",
            nbins=20, barmode="overlay", opacity=0.75,
            color_discrete_map=color_map,
            labels={"score": "DiT Confidence Score", "count": "Number of documents", "status": "Status"},
            range_x=[0, 1],
        )
        fig_dit.add_vline(x=0.3725, line_dash="dash", line_color="white",
                          annotation_text="Decision threshold (0.3725)",
                          annotation_position="top right",
                          annotation_font_color="white")
        fig_dit.update_layout(
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            height=320,
            legend=dict(orientation="h", yanchor="bottom", y=1.02),
            xaxis=dict(tickformat=".1f", dtick=0.1),
        )
        st.plotly_chart(fig_dit, use_container_width=True)
    else:
        st.info("No DiT scores available yet.")

with col_time:
    st.subheader("Processing Timeline")
    st.caption("Number of documents processed per day, by outcome.")

    if timeline:
        df_time = pd.DataFrame(timeline)
        df_time["day"] = pd.to_datetime(df_time["day"])
        color_map_t = {
            "validated":   "#2ecc71",
            "need_review": "#f39c12",
            "rejected":    "#e74c3c",
        }
        fig_time = px.bar(
            df_time, x="day", y="count", color="status",
            barmode="stack",
            color_discrete_map=color_map_t,
            labels={"day": "Date", "count": "Documents", "status": "Status"},
        )
        fig_time.update_layout(
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            height=320,
            legend=dict(orientation="h", yanchor="bottom", y=1.02),
            xaxis_tickformat="%d %b",
        )
        st.plotly_chart(fig_time, use_container_width=True)
    else:
        st.info("No timeline data available yet.")

st.markdown("---")

# ── 3. Enriched Category Table + Status Pie ───────────────────────────────────
col_cat, col_pie = st.columns([3, 2])

with col_cat:
    st.subheader("Expense Categories — Detail")
    st.caption("Validated invoices only — amounts in MAD.")

    if by_category:
        df_cat = pd.DataFrame(by_category)
        df_cat.columns = ["Category", "Count", "Amount"]
        df_cat["Amount"] = df_cat["Amount"].astype(float).fillna(0)
        df_cat["Avg per Invoice"] = (df_cat["Amount"] / df_cat["Count"]).round(2)
        df_cat["% of Total"] = (df_cat["Amount"] / df_cat["Amount"].sum() * 100).round(1).astype(str) + "%"
        df_cat["Amount"] = df_cat["Amount"].map(lambda x: f"{x:,.2f}")
        df_cat["Avg per Invoice"] = df_cat["Avg per Invoice"].map(lambda x: f"{x:,.2f}")
        df_cat = df_cat.sort_values("Count", ascending=False).reset_index(drop=True)
        st.dataframe(
            df_cat[["Category", "Count", "Amount", "Avg per Invoice", "% of Total"]],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("No validated invoices yet.")

with col_pie:
    st.subheader("Status Breakdown")
    if total > 0:
        fig_pie = go.Figure(data=[go.Pie(
            labels=["Validated", "Rejected (DiT)", "Needs Review"],
            values=[validated, rejected, need_review],
            marker_colors=["#2ecc71", "#e74c3c", "#f39c12"],
            hole=0.55,
            textinfo="label+percent",
            hovertemplate="%{label}: %{value} documents<extra></extra>",
        )])
        fig_pie.update_layout(
            showlegend=False,
            height=320,
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            margin=dict(t=10, b=10, l=10, r=10),
            annotations=[dict(
                text=f"{total}<br>total",
                x=0.5, y=0.5,
                font_size=16,
                showarrow=False,
            )],
        )
        st.plotly_chart(fig_pie, use_container_width=True)
    else:
        st.info("No data yet.")

st.markdown("---")

# ── 4. Recent Invoices ────────────────────────────────────────────────────────
st.subheader("Recent Invoices")
if recent:
    df_recent = pd.DataFrame(recent)
    cols_display = ["vendor_name", "invoice_date", "total_amount",
                    "currency", "expense_category", "status", "source"]
    df_display = df_recent[[c for c in cols_display if c in df_recent.columns]]
    df_display = df_display.rename(columns={
        "vendor_name":      "Vendor",
        "invoice_date":     "Date",
        "total_amount":     "Amount",
        "currency":         "Currency",
        "expense_category": "Category",
        "status":           "Status",
        "source":           "Source",
    })
    status_labels = {"validated": "Validated", "rejected": "Rejected", "need_review": "Needs Review"}
    if "Status" in df_display.columns:
        df_display["Status"] = df_display["Status"].map(lambda s: status_labels.get(s, s))
    st.dataframe(df_display, use_container_width=True, hide_index=True)
else:
    st.info("No invoices processed yet. Use **Upload Invoice** or **Run Pipeline** to get started!")
