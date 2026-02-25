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
from ui.tabs.concession_tab import render_concession_tab
from ui.tabs.findings_tab import render_findings_tab
from ui.tabs.report_tab import render_report_tab

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
# Sidebar — new version with OpenAI key + model selector
# ---------------------------------------------------------------------------

def render_new_sidebar():
    """Render the updated sidebar with OpenAI controls."""
    st.sidebar.title(f"{settings.APP_ICON} {settings.APP_TITLE}")
    st.sidebar.markdown("---")

    # OpenAI API key
    st.sidebar.subheader("🔑 OpenAI API Key")
    env_key = os.environ.get("OPENAI_API_KEY", "")
    api_key = st.sidebar.text_input(
        "API Key (or set OPENAI_API_KEY env var)",
        value=env_key,
        type="password",
        help="Required to run the AI audit agent.",
    )

    # Model selector
    model = st.sidebar.selectbox(
        "Model",
        options=["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"],
        index=0,
    )

    st.sidebar.markdown("---")

    # File uploader
    st.sidebar.subheader("📤 Upload Files")
    uploaded_files = st.sidebar.file_uploader(
        "Upload audit documents",
        type=["csv", "xlsx", "xls", "pdf", "docx", "doc"],
        accept_multiple_files=True,
        help="Supported: CSV, Excel, PDF, Word",
    )

    # Show detected document types
    if uploaded_files:
        st.sidebar.markdown("**Detected document types:**")
        from ingestion.parsers import detect_document_type
        for uf in uploaded_files:
            dtype = detect_document_type(uf.name)
            badge = {
                "rent_roll": "📋",
                "projection": "📊",
                "concession": "💰",
                "unknown": "❓",
            }.get(dtype, "❓")
            st.sidebar.markdown(f"{badge} `{uf.name}` → **{dtype}**")

    st.sidebar.markdown("---")
    run_audit_btn = st.sidebar.button("🚀 Run AI Audit", type="primary", disabled=not uploaded_files)

    return {
        "api_key": api_key,
        "model": model,
        "uploaded_files": uploaded_files or [],
        "run_audit": run_audit_btn,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    initialize_session_state()
    sidebar = render_new_sidebar()
    canonical_model: CanonicalModel = st.session_state.canonical_model
    audit_log: AuditLog = st.session_state.audit_log

    st.title(f"{settings.APP_ICON} {settings.APP_TITLE}")
    st.markdown("---")

    uploaded_files = sidebar["uploaded_files"]

    # Welcome screen
    if not uploaded_files:
        st.info(
            "👆 **Get started:** Upload one or more files using the sidebar, then click **Run AI Audit**.\n\n"
            "Supported file types: CSV, Excel (.xlsx/.xls), PDF, Word (.docx)\n\n"
            "Sample fixtures are available in `data/samples/`:\n"
            "- `rent_roll_sample.csv` — example rent roll\n"
            "- `projection_sample.csv` — example recurring transaction projection\n"
            "- `recurring_transaction_projection.pdf` — example PDF report"
        )
        return

    # Load files when they first appear or change
    file_names = [f.name for f in uploaded_files]
    if file_names != st.session_state.get("_last_file_names"):
        st.session_state["_last_file_names"] = file_names
        st.session_state.data_loaded = False
        st.session_state.audit_result = None
        canonical_model.clear()
        st.session_state.parsed_docs = []

    if not st.session_state.data_loaded:
        with st.spinner("Parsing uploaded files…"):
            ok_count, errors, parsed_docs = load_files(uploaded_files, canonical_model, audit_log)
        if ok_count > 0:
            st.success(f"✅ Loaded {ok_count} file(s)")
            st.session_state.data_loaded = True
            st.session_state.parsed_docs = parsed_docs
        for err in errors:
            st.error(f"• {err}")

    parsed_docs: List[ParsedDocument] = st.session_state.parsed_docs

    # Detect content types
    doc_types = {d.document_type for d in parsed_docs}
    has_rent_roll = "rent_roll" in doc_types
    has_projection = "projection" in doc_types
    has_concessions = "concession" in doc_types

    rent_roll_doc: Optional[ParsedDocument] = next(
        (d for d in parsed_docs if d.document_type == "rent_roll"), None
    )
    projection_doc: Optional[ParsedDocument] = next(
        (d for d in parsed_docs if d.document_type == "projection"), None
    )

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

    # --- Content-aware tabs ---
    tabs_labels: List[str] = []
    if has_rent_roll:
        tabs_labels.append("📋 Rent Roll")
    if has_projection:
        tabs_labels.append("📊 Projections")
    if has_concessions:
        tabs_labels.append("💰 Concessions")
    tabs_labels += ["🔍 AI Findings", "📄 Full Report", "🗂️ Raw Data"]

    tabs = st.tabs(tabs_labels)
    tab_idx = 0

    if has_rent_roll:
        with tabs[tab_idx]:
            render_rent_roll_tab(rent_roll_doc)
        tab_idx += 1

    if has_projection:
        with tabs[tab_idx]:
            render_projection_tab(projection_doc)
        tab_idx += 1

    if has_concessions:
        with tabs[tab_idx]:
            render_concession_tab(parsed_docs)
        tab_idx += 1

    with tabs[tab_idx]:
        render_findings_tab(audit_result)
    tab_idx += 1

    with tabs[tab_idx]:
        render_report_tab(audit_result, st.session_state.get("audit_timestamp"))
    tab_idx += 1

    with tabs[tab_idx]:
        st.subheader("🗂️ Raw Data")
        for doc in parsed_docs:
            with st.expander(f"{doc.file_name} ({doc.document_type})", expanded=False):
                if doc.dataframe is not None and not doc.dataframe.empty:
                    st.dataframe(doc.dataframe, use_container_width=True)
                else:
                    st.text(doc.raw_text[:3000] if doc.raw_text else "No content extracted.")

    st.markdown("---")
    st.caption(f"{settings.APP_TITLE} | {datetime.now().strftime('%Y-%m-%d %H:%M')}")


if __name__ == "__main__":
    main()
