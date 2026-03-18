"""
Village Green Property Recurring Transaction & Concession Audit System
Main Streamlit Application — content-aware tabbed interface with LangGraph AI agent
"""
import streamlit as st
import tempfile
import os
from pathlib import Path
from datetime import datetime
from typing import List, Optional

# Import audit engine
from audit_engine import compute_metrics

# Import models and engines (existing)
from models.canonical_model import CanonicalModel
from engine.date_range_engine import DateRangeEngine
from engine.anomaly_detector import AnomalyDetector
from engine.explainability import ExplainabilityEngine
from engine.langgraph_engine import LangGraphEngine

# Import ingestion
from ingestion.loader import FileLoader
from ingestion.parsers import ParsedDocument
from ingestion.resman_client import ResManClient

# Import storage
from storage.database import Database
from storage.audit_log import AuditLog

# Import UI components (existing)
from ui.filters import render_sidebar
from ui.dashboard import render_kpi_overview, render_summary_stats
from ui.charts import render_revenue_trend, render_concession_analysis, render_lease_cliff_heatmap
from ui.unit_view import render_unit_drilldown
from ui.findings import render_findings_table, render_findings_summary
from ui.override import render_override_panel, render_audit_trail
from ui.export import render_export_panel

# Import new tabbed UI
from ui.tabs.rent_roll_tab import render_rent_roll_tab
from ui.tabs.projection_tab import render_projection_tab
from ui.tabs.findings_tab import render_findings_tab
from ui.tabs.report_tab import render_report_tab
from ui.tabs.concession_tab import render_concession_tab
from ui.tabs.revenue_integrity_tab import render_revenue_integrity_tab
from ui.tabs.overrides_tab import render_overrides_tab
from ui.tabs.exposure_tab import render_exposure_tab
from ui.tabs.fee_schedule_tab import render_fee_schedule_tab

# Import config
from config import settings

# Page configuration
st.set_page_config(
    page_title=settings.APP_TITLE,
    page_icon=settings.APP_ICON,
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Custom theme / CSS
# ---------------------------------------------------------------------------
st.markdown("""
<style>
/* ── Sidebar ── */
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
}
[data-testid="stSidebar"] * {
    color: #e0e0e0 !important;
}
[data-testid="stSidebar"] h1,
[data-testid="stSidebar"] h2,
[data-testid="stSidebar"] h3 {
    color: #ffffff !important;
}
[data-testid="stSidebar"] .stSelectbox label,
[data-testid="stSidebar"] .stTextInput label,
[data-testid="stSidebar"] .stFileUploader label {
    color: #c0c8d8 !important;
    font-weight: 500;
}
[data-testid="stSidebar"] .stSelectbox [data-baseweb="select"],
[data-testid="stSidebar"] .stTextInput input {
    background-color: rgba(255,255,255,0.08) !important;
    border: 1px solid rgba(255,255,255,0.15) !important;
    color: #d0d0d0 !important;
}
[data-testid="stSidebar"] .stSelectbox [data-baseweb="select"] * {
    color: #d0d0d0 !important;
}
[data-testid="stSidebar"] .stTextInput input::placeholder {
    color: #808898 !important;
}
[data-testid="stSidebar"] [data-testid="stFileUploader"] {
    background-color: rgba(255,255,255,0.06) !important;
    border: 1px dashed rgba(255,255,255,0.2) !important;
    border-radius: 8px;
    padding: 8px;
}
[data-testid="stSidebar"] [data-testid="stFileUploader"] button {
    background-color: rgba(255,255,255,0.1) !important;
    color: #c0c8d8 !important;
    border: 1px solid rgba(255,255,255,0.2) !important;
}
[data-testid="stSidebar"] .stButton > button {
    background: linear-gradient(135deg, #e94560 0%, #c23152 100%);
    color: #ffffff !important;
    border: none;
    font-weight: 600;
    letter-spacing: 0.3px;
    transition: all 0.2s;
}
[data-testid="stSidebar"] .stButton > button:hover {
    background: linear-gradient(135deg, #ff6b81 0%, #e94560 100%);
    transform: translateY(-1px);
    box-shadow: 0 4px 12px rgba(233,69,96,0.4);
}
[data-testid="stSidebar"] hr {
    border-color: rgba(255,255,255,0.12) !important;
}
[data-testid="stSidebar"] .stMarkdown p {
    color: #b0b8c8 !important;
}

/* ── Main area subtle improvements ── */
[data-testid="stAppViewContainer"] {
    background-color: #f0f2f6;
}
[data-testid="stMain"] {
    background-color: #e8eaef;
}
.stTabs [data-baseweb="tab-list"] {
    gap: 4px;
}
.stTabs [data-baseweb="tab"] {
    padding: 8px 16px;
    border-radius: 8px 8px 0 0;
}
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Session state helpers
# ---------------------------------------------------------------------------

def initialize_session_state():
    """Initialize session state variables."""
    defaults = {
        "canonical_model": CanonicalModel(),
        "data_loaded": False,
        "audit_log": AuditLog(),
        "database": Database(),
        "parsed_docs": [],
        "audit_result": None,
        "audit_timestamp": None,
        "saved_api_key": os.environ.get("OPENAI_API_KEY", ""),
        "resman_results": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


# ---------------------------------------------------------------------------
# Data loading helpers
# ---------------------------------------------------------------------------

def load_files(
    uploaded_files,
    canonical_model: CanonicalModel,
    audit_log: AuditLog,
) -> tuple[int, List[str], List[ParsedDocument]]:
    """Load uploaded files, returning (success_count, errors, parsed_docs)."""
    loader = FileLoader()
    success_count = 0
    error_messages: List[str] = []
    parsed_docs: List[ParsedDocument] = []

    with tempfile.TemporaryDirectory() as tmp:
        for uf in uploaded_files:
            tmp_path = os.path.join(tmp, uf.name)
            with open(tmp_path, "wb") as f:
                f.write(uf.getbuffer())

            ok, msg, parsed_doc = loader.load_file(tmp_path, canonical_model)
            if ok:
                success_count += 1
                if parsed_doc is not None:
                    parsed_docs.append(parsed_doc)
            else:
                error_messages.append(f"{uf.name}: {msg}")

    if success_count > 0:
        audit_log.log_data_load(
            source="file_upload",
            file_name=f"{success_count} files",
            user="System",
            records_loaded=len(canonical_model.transactions),
        )

    return success_count, error_messages, parsed_docs


# ---------------------------------------------------------------------------
# Sidebar — v4-style with LiveNjoy branding; AI features below forensic button
# ---------------------------------------------------------------------------

def render_new_sidebar():
    """Render the sidebar matching the v4 layout."""
    from config.fee_schedules import APPROVED_CODES as _APPROVED_CODES

    with st.sidebar:
        st.image("https://img.icons8.com/fluency/96/property.png", width=60)
        st.title("LiveNjoy Audit Bot")
        st.markdown("**Version:** 2.0  \n**Engine:** John + Daniel Rules")
        st.divider()

        st.markdown("**Approved Concession Codes**")
        for code in sorted(_APPROVED_CODES):
            st.markdown(
                f"- <code style='background:rgba(255,255,255,0.1); color:inherit; padding:2px 6px; border-radius:4px;'>{code}</code>",
                unsafe_allow_html=True,
            )
        st.divider()

        run_forensic_btn = st.button(
            "🚀 Run Full Forensic Audit",
            type="primary",
            use_container_width=True,
        )
        st.divider()

        st.markdown("**File Setup Guide**")
        st.markdown(
            "Copy your exports into these folders:"
            "\n```"
            "\nexports/Transaction List Reports/"
            "\n  → data/transactions/"
            "\nexports/New & Renewed Leases/"
            "\n  → data/leases/"
            "\nexports/Edited Transactions by User/"
            "\n  → data/edits/"
            "\nexports/Transaction Projections/"
            "\n  → data/recurring/"
            "\nexports/Rent Rolls/"
            "\n  → data/rent_rolls/"
            "\nexports/Resident Activity/"
            "\n  → data/activity/"
            "\n```"
            "\n⚠️ Resident Ledgers are PDFs — not processed by the bot."
        )
        st.divider()

        # --- AI Audit section (secondary) ---
        st.subheader("🤖 AI Audit (Optional)")

        env_key = os.environ.get("OPENAI_API_KEY", "")
        saved_key = st.session_state.get("saved_api_key", env_key)
        api_key_input = st.text_input(
            "OpenAI API Key",
            value=saved_key,
            type="password",
            help="Required to run the AI audit agent.",
        )

        btn_col1, btn_col2 = st.columns(2)
        with btn_col1:
            if st.button("💾 Save", key="save_api_key"):
                if api_key_input.strip():
                    st.session_state["saved_api_key"] = api_key_input.strip()
                    st.success("Saved")
                else:
                    st.warning("Enter a key first")
        with btn_col2:
            if st.button("✖ Cancel", key="cancel_api_key"):
                st.session_state["saved_api_key"] = env_key
                st.rerun()

        api_key = st.session_state.get("saved_api_key", api_key_input)

        model = st.selectbox(
            "Model",
            options=["o3", "o4-mini", "gpt-4.1", "gpt-4.1-mini", "gpt-4o", "gpt-4o-mini"],
            index=0,
            help="o3 = best reasoning; o4-mini = fast reasoning; gpt-4.1 = latest GPT",
        )

        st.markdown("**Upload Files for AI Audit**")
        uploaded_files = st.file_uploader(
            "Upload audit documents",
            type=["csv", "xlsx", "xls", "pdf", "docx"],
            accept_multiple_files=True,
            help="Supported: CSV, Excel, PDF, Word (.docx)",
        )

        if uploaded_files:
            from ingestion.parsers import detect_document_type
            for uf in uploaded_files:
                dtype = detect_document_type(uf.name)
                badge = {"rent_roll": "📋", "projection": "📊", "concession": "💰"}.get(dtype, "❓")
                st.markdown(f"{badge} `{uf.name}` → **{dtype}**")

        has_data = bool(uploaded_files)
        run_audit_btn = st.button("🚀 Run AI Audit", type="secondary", disabled=not has_data)

    return {
        "api_key": api_key,
        "model": model,
        "uploaded_files": uploaded_files or [],
        "run_audit": run_audit_btn,
        "run_forensic": run_forensic_btn,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    initialize_session_state()

    sidebar = render_new_sidebar()
    canonical_model: CanonicalModel = st.session_state.canonical_model
    audit_log: AuditLog = st.session_state.audit_log

    uploaded_files = sidebar["uploaded_files"]

    # --- Header ---
    st.title("📊 LiveNjoy — Master Audit Dashboard")
    st.markdown(
        "Automated **Concession Audit** (John's Rules: Post-Term, Missing Addendum, "
        "Amount Mismatch, Not Properly Posted, Large Credit, Non-Standard Description) + "
        "**Recurring Revenue Integrity Audit** (Daniel's 2-Stage Engine)"
    )
    st.divider()

    # Run Forensic audit when button pressed
    if sidebar.get("run_forensic"):
        with st.spinner("🔬 Running forensic rules engine…"):
            try:
                from engine.resman_rules import run_resman_audit
                results = run_resman_audit(data_dir="data")
                st.session_state["resman_results"] = results
                st.success("✅ Forensic audit complete — dashboard updated.")
            except Exception as e:
                st.error(f"Forensic engine error: {e}")

    # Load uploaded files
    file_names = [f.name for f in uploaded_files]
    if file_names != st.session_state.get("_last_file_names"):
        st.session_state["_last_file_names"] = file_names
        st.session_state.data_loaded = False
        st.session_state.audit_result = None
        canonical_model.clear()
        st.session_state.parsed_docs = []

    if not st.session_state.data_loaded and uploaded_files:
        with st.spinner("Parsing uploaded files…"):
            ok_count, errors, parsed_docs = load_files(uploaded_files, canonical_model, audit_log)
        if ok_count > 0:
            st.success(f"✅ Loaded {ok_count} file(s)")
            st.session_state.data_loaded = True
            st.session_state.parsed_docs = parsed_docs
        for err in errors:
            st.error(f"• {err}")

    parsed_docs: List[ParsedDocument] = st.session_state.parsed_docs

    # Run AI audit when button pressed
    if sidebar["run_audit"]:
        api_key = sidebar["api_key"]
        if not api_key:
            st.error(
                "❌ No OpenAI API key provided. "
                "Enter your key in the sidebar or set the `OPENAI_API_KEY` environment variable."
            )
        else:
            os.environ["AUDIT_MODEL"] = sidebar["model"]
            with st.spinner("🤖 Running AI audit agent… this may take a minute…"):
                try:
                    engine = LangGraphEngine(api_key=api_key)
                    result = engine.run(canonical_model, parsed_docs=parsed_docs)
                    st.session_state.audit_result = result
                    st.session_state.audit_timestamp = datetime.now()
                    st.success(
                        f"✅ Audit complete at {st.session_state.audit_timestamp.strftime('%Y-%m-%d %H:%M:%S')}"
                    )
                except ValueError as e:
                    st.error(str(e))
                except Exception as e:
                    st.error(f"Audit agent error: {e}")

    audit_result = st.session_state.get("audit_result")
    resman_results = st.session_state.get("resman_results")

    # --- No results yet: show prompt ---
    if resman_results is None and audit_result is None and not uploaded_files:
        st.info("👈 Click **Run Full Forensic Audit** in the sidebar to begin.")
        return

    # --- Build tab list ---
    # Forensic audit tabs are PRIMARY (shown first when available)
    tabs_labels: List[str] = []
    if resman_results is not None:
        tabs_labels += [
            "📈 Executive Summary",
            "🔍 Concession Audit (John)",
            "⚙️ Revenue Integrity (Daniel)",
            "👤 Manager Overrides",
            "💰 Exposure Drilldowns",
            "🗂️ Risk Matrix",
            "📋 Fee Schedule Check",
        ]

    # AI audit tabs (secondary — shown after forensic tabs)
    doc_types = {d.document_type for d in parsed_docs}
    has_rent_roll = "rent_roll" in doc_types
    has_projection = "projection" in doc_types
    rent_roll_doc: Optional[ParsedDocument] = next(
        (d for d in parsed_docs if d.document_type == "rent_roll"), None
    )
    projection_doc: Optional[ParsedDocument] = next(
        (d for d in parsed_docs if d.document_type == "projection"), None
    )

    if has_rent_roll:
        tabs_labels.append("📋 Rent Roll")
    if has_projection:
        tabs_labels.append("📊 Projections")
    if audit_result is not None or uploaded_files:
        tabs_labels += ["🔍 AI Findings", "📄 Full Report"]
    if parsed_docs:
        tabs_labels.append("🗂️ Raw Data")

    if not tabs_labels:
        st.info("👈 Click **Run Full Forensic Audit** in the sidebar to begin.")
        return

    tabs = st.tabs(tabs_labels)
    tab_idx = 0

    # ── Forensic audit tabs ────────────────────────────────────────────────
    if resman_results is not None:
        import pandas as _pd

        johns_flags = resman_results.get("johns_flags", _pd.DataFrame())
        daniels_flags = resman_results.get("daniels_flags", _pd.DataFrame())
        fee_flags = resman_results.get("fee_flags", _pd.DataFrame())
        all_flags = resman_results.get("all_flags", _pd.DataFrame())
        manager_ranking = resman_results.get("manager_ranking", _pd.DataFrame())
        override_log = resman_results.get("override_log", _pd.DataFrame())
        exposure = resman_results.get("exposure", {})

        from config.fee_schedules import RISK_CRITICAL, RISK_HIGH, RISK_MEDIUM

        RISK_COLORS_MAP = {
            RISK_CRITICAL: "#FF4B4B",
            RISK_HIGH: "#FFA500",
            RISK_MEDIUM: "#FFD700",
        }

        def _color_risk_v4(val):
            color = RISK_COLORS_MAP.get(val, "#FFFFFF")
            return f"background-color: {color}; color: black; font-weight: bold;"

        # Tab 1: Executive Summary
        with tabs[tab_idx]:
            st.header("Portfolio Health Snapshot")
            totals = exposure.get("totals", _pd.DataFrame())

            if not totals.empty:
                row = totals.iloc[0]
                c1, c2, c3, c4, c5 = st.columns(5)
                c1.metric("Units Audited", int(row.get("Total_Units_Audited", 0)))
                c2.metric("Total Exceptions", int(row.get("Total_Exceptions", 0)))
                c3.metric("Financial Exposure", f"${row.get('Deduped_Exposure', row.get('Total_Exposure', 0)):,.2f}")
                c4.metric("Error Rate", f"{row.get('Error_Pct', 0):.1f}%")
                c5.metric("Critical Flags", int(row.get("Critical_Flags", 0)))
                st.divider()
                rc1, rc2, rc3 = st.columns(3)
                rc1.metric("🔴 CRITICAL", int(row.get("Critical_Flags", 0)))
                rc2.metric("🟠 HIGH", int(row.get("High_Flags", 0)))
                rc3.metric("🟡 MEDIUM", int(row.get("Medium_Flags", 0)))

            st.divider()
            st.subheader("All Exceptions")
            if not all_flags.empty:
                f_cols = st.columns(3)
                with f_cols[0]:
                    risk_f = st.multiselect(
                        "Risk Level",
                        [RISK_CRITICAL, RISK_HIGH, RISK_MEDIUM],
                        default=[RISK_CRITICAL, RISK_HIGH, RISK_MEDIUM],
                        key="exec_risk",
                    )
                with f_cols[1]:
                    prop_opts = ["All"] + sorted(all_flags["Property"].dropna().unique().tolist())
                    prop_f = st.selectbox("Property", prop_opts, key="exec_prop")
                with f_cols[2]:
                    rule_opts = ["All"] + sorted(all_flags["Rule"].dropna().unique().tolist())
                    rule_f = st.selectbox("Rule", rule_opts, key="exec_rule")

                view = all_flags[all_flags["Risk_Level"].isin(risk_f)]
                if prop_f != "All":
                    view = view[view["Property"] == prop_f]
                if rule_f != "All":
                    view = view[view["Rule"] == rule_f]

                if "Risk_Level" in view.columns:
                    st.dataframe(
                        view.style.map(_color_risk_v4, subset=["Risk_Level"]),
                        use_container_width=True,
                        hide_index=True,
                    )
                else:
                    st.dataframe(view, use_container_width=True, hide_index=True)
                st.caption(f"{len(view):,} records shown")
            else:
                st.success("✅ No exceptions found — clean portfolio!")
        tab_idx += 1

        # Tab 2: Concession Audit (John)
        with tabs[tab_idx]:
            render_concession_tab(
                parsed_docs=None,
                resman_docs=None,
                johns_flags=johns_flags,
            )
        tab_idx += 1

        # Tab 3: Revenue Integrity (Daniel)
        with tabs[tab_idx]:
            render_revenue_integrity_tab(daniels_flags)
        tab_idx += 1

        # Tab 4: Manager Overrides
        with tabs[tab_idx]:
            render_overrides_tab(manager_ranking, override_log)
        tab_idx += 1

        # Tab 5: Exposure Drilldowns
        with tabs[tab_idx]:
            render_exposure_tab(exposure, override_log)
        tab_idx += 1

        # Tab 6: Risk Matrix
        with tabs[tab_idx]:
            st.header("Risk Matrix — Severity by Property")
            if all_flags.empty:
                st.success("No flags — nothing to display.")
            else:
                pivot = (
                    all_flags.groupby(["Property", "Risk_Level"])
                    .agg(Count=("Rule", "count"), Exposure=("Amount_Impact", "sum"))
                    .reset_index()
                    .pivot_table(
                        index="Property",
                        columns="Risk_Level",
                        values=["Count", "Exposure"],
                        fill_value=0,
                    )
                )
                pivot.columns = [f"{v}_{c}" for v, c in pivot.columns]
                pivot = pivot.reset_index()
                st.dataframe(pivot, use_container_width=True)

                st.divider()
                st.subheader("Resident-Level Drilldown")
                props = sorted(all_flags["Property"].dropna().unique().tolist())
                selected_prop = st.selectbox("Select Property", ["All"] + props, key="risk_matrix_prop")
                drilldown = (
                    all_flags if selected_prop == "All"
                    else all_flags[all_flags["Property"] == selected_prop]
                )
                drilldown_sorted = drilldown.sort_values(
                    ["Risk_Level", "Amount_Impact"],
                    key=lambda col: (
                        col.map({RISK_CRITICAL: 0, RISK_HIGH: 1, RISK_MEDIUM: 2})
                        if col.name == "Risk_Level"
                        else col
                    ),
                    ascending=[True, False],
                )
                st.dataframe(
                    drilldown_sorted.style.map(_color_risk_v4, subset=["Risk_Level"])
                    if "Risk_Level" in drilldown_sorted.columns
                    else drilldown_sorted,
                    use_container_width=True,
                    hide_index=True,
                )
                st.caption(
                    f"{len(drilldown_sorted):,} exceptions | "
                    f"Exposure: **${drilldown_sorted['Amount_Impact'].sum():,.2f}**"
                )
        tab_idx += 1

        # Tab 7: Fee Schedule Check
        with tabs[tab_idx]:
            render_fee_schedule_tab(fee_flags)
        tab_idx += 1

    # ── AI audit tabs ──────────────────────────────────────────────────────
    if has_rent_roll:
        with tabs[tab_idx]:
            render_rent_roll_tab(rent_roll_doc)
        tab_idx += 1

    if has_projection:
        with tabs[tab_idx]:
            render_projection_tab(projection_doc)

            if (
                projection_doc is not None
                and projection_doc.dataframe is not None
                and not projection_doc.dataframe.empty
            ):
                rent_roll_df = (
                    rent_roll_doc.dataframe
                    if rent_roll_doc is not None and rent_roll_doc.dataframe is not None
                    else None
                )
                try:
                    filtered_df = compute_metrics(projection_doc.dataframe, rent_roll_df)
                    if not filtered_df.empty:
                        st.markdown("---")
                        st.subheader("📊 Portfolio Risk Metrics")
                        m1, m2, m3 = st.columns(3)
                        m1.metric("Monthly Leakage", f"${filtered_df['Monthly_Projection'].abs().sum():,.2f}")
                        m2.metric("Units Tracked", f"{len(filtered_df)}")
                        m3.metric("Total Portfolio Risk", f"${filtered_df['Total_Lease_Loss'].abs().sum():,.2f}")
                except Exception as e:
                    st.warning(f"Could not compute portfolio risk metrics: {e}")
        tab_idx += 1

    if audit_result is not None or uploaded_files:
        with tabs[tab_idx]:
            render_findings_tab(audit_result, parsed_docs=parsed_docs)
        tab_idx += 1

        with tabs[tab_idx]:
            render_report_tab(audit_result, st.session_state.get("audit_timestamp"))
        tab_idx += 1

    if parsed_docs:
        with tabs[tab_idx]:
            st.subheader("🗂️ Raw Data")
            for doc in parsed_docs:
                with st.expander(f"{doc.file_name} ({doc.document_type})", expanded=False):
                    if doc.dataframe is not None and not doc.dataframe.empty:
                        st.dataframe(doc.dataframe, use_container_width=True)
                    else:
                        st.text(doc.raw_text[:3000] if doc.raw_text else "No content extracted.")
        tab_idx += 1

    st.markdown("---")
    st.caption(f"{settings.APP_TITLE} | {datetime.now().strftime('%Y-%m-%d %H:%M')}")


if __name__ == "__main__":
    main()
