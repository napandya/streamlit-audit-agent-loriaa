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

# Import data loader
from utils.data_loader import load_resman_csvs_from_data_dir

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
        "resman_concession_docs": [],
        "_resman_docs_loaded": False,
        "audit_prompt": None,
        "custom_prompt": None,
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
        options=["o3", "o4-mini", "gpt-4.1", "gpt-4.1-mini", "gpt-4o", "gpt-4o-mini"],
        index=0,
        help="o3 = best reasoning; o4-mini = fast reasoning; gpt-4.1 = latest GPT",
    )

    st.sidebar.markdown("---")

    # File uploader
    st.sidebar.subheader("📤 Upload Files")
    uploaded_files = st.sidebar.file_uploader(
        "Upload audit documents",
        type=["csv", "xlsx", "xls", "pdf", "docx"],
        accept_multiple_files=True,
        help="Supported: CSV, Excel, PDF, Word (.docx)",
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
    has_data = bool(uploaded_files) or bool(st.session_state.get("resman_concession_docs"))
    run_audit_btn = st.sidebar.button("🚀 Run AI Audit", type="primary", disabled=not has_data)

    return {
        "api_key": api_key,
        "model": model,
        "uploaded_files": uploaded_files or [],
        "run_audit": run_audit_btn,
    }


# ---------------------------------------------------------------------------
# Default audit prompt (used as starting point for the editor)
# ---------------------------------------------------------------------------

_DEFAULT_AUDIT_PROMPT = (
    "You are a senior property management audit expert analyzing ResMan Transaction List "
    "CSV files for concession anomalies. You have data from MULTIPLE properties.\n\n"
    "CRITICAL REQUIREMENT — PER-FILE ANALYSIS:\n"
    "You MUST analyze EACH CSV file SEPARATELY and produce a dedicated section for each.\n"
    "For each file, create a section with:\n"
    "  ## <Property Name> — <filename>\n\n"
    "Then within each section, list every finding with:\n"
    "  ### Finding: <short title>\n"
    "  **Severity:** 🔴 Critical / 🟠 High / 🟡 Medium / 🟢 Low\n"
    "  **Affected Units:** <unit numbers>\n"
    "  **Citation:** [Source: <filename>, Row <number>]\n"
    "  **Description:** <what was found>\n"
    "  **Reasoning:** <complete chain of reasoning>\n"
    "  **Recommended Action:** <specific corrective action>\n\n"
    "WHAT TO LOOK FOR IN EACH FILE:\n"
    "1. $999 Specials — concessions reducing rent to exactly $999.\n"
    "2. Excessive concessions > $1,000.\n"
    "3. Reversed concessions (rows with Reverse Date).\n"
    "4. Move-in specials ($99 / $0 deals).\n"
    "5. Duplicate unit concessions in one period.\n"
    "6. Generic 'Concession - Rent' descriptions.\n"
    "7. Large total concession amounts per property.\n"
    "8. Active vs reversed ratio anomalies.\n\n"
    "Start with an Executive Summary, then one section per CSV, end with Recommendations."
)


# ---------------------------------------------------------------------------
# Prompt Editor tab
# ---------------------------------------------------------------------------

def _render_prompt_editor_tab(audit_result):
    """Render the prompt editor tab with the prompt used and ability to edit/re-run."""
    st.subheader("⚙️ Audit Prompt Editor")
    st.caption(
        "View and customize the prompt sent to the AI audit agent. "
        "Edit the prompt below, then click **Re-run Audit with Custom Prompt** in the sidebar."
    )

    # Show the prompt that was used for the last audit
    last_prompt = st.session_state.get("audit_prompt")
    if last_prompt:
        with st.expander("📋 Prompt used in last audit run", expanded=False):
            st.code(last_prompt, language="markdown")

    # Editable prompt
    st.markdown("### ✏️ Edit Prompt")
    st.markdown(
        "Modify the instructions below to change what the AI looks for. "
        "The **DATA SUMMARY** (your CSV data) is automatically appended — "
        "you only need to edit the instructions."
    )

    current_custom = st.session_state.get("custom_prompt") or ""
    default_value = current_custom if current_custom else _DEFAULT_AUDIT_PROMPT

    edited_prompt = st.text_area(
        "Audit prompt (instructions to the AI agent)",
        value=default_value,
        height=400,
        key="prompt_editor_textarea",
    )

    col1, col2, col3 = st.columns([1, 1, 2])
    with col1:
        if st.button("💾 Save Custom Prompt", type="primary"):
            st.session_state.custom_prompt = edited_prompt
            st.success("Custom prompt saved. Click **🚀 Run AI Audit** in the sidebar to use it.")
    with col2:
        if st.button("🔄 Reset to Default"):
            st.session_state.custom_prompt = None
            st.rerun()

    st.markdown("---")

    # Quick prompt suggestions
    st.markdown("### 💡 Prompt Templates")
    st.markdown("Click to load a pre-built prompt into the editor:")

    templates = {
        "🔍 Deep Concession Analysis": (
            "You are a forensic property auditor specializing in concession analysis. "
            "Examine every concession in the data. For each one:\n"
            "1. Identify the type (move-in special, rent reduction, employee allowance, etc.)\n"
            "2. Calculate the effective rent after concession\n"
            "3. Flag any concession that reduces rent below $999\n"
            "4. Flag duplicate concessions on the same unit\n"
            "5. Flag reversed concessions that may not have been properly re-applied\n"
            "6. Check if employee units have additional unauthorized concessions\n\n"
            "For EVERY finding, provide:\n"
            "- Citation: `[Source: <filename>, Row <number>]`\n"
            "- Why: Complete reasoning chain explaining the issue\n"
            "- Impact: Estimated monthly revenue impact\n"
            "- Action: Specific recommended next step\n\n"
            "Format as a structured Markdown report grouped by severity."
        ),
        "📊 Revenue Risk Focus": (
            "You are a property management CFO reviewing concession data for revenue leakage. "
            "Focus specifically on:\n"
            "1. Total concession dollar amount by property\n"
            "2. Concessions as a percentage of gross rent\n"
            "3. Units with the largest absolute concession amounts\n"
            "4. Patterns that suggest systemic pricing issues (e.g., many $999 specials)\n"
            "5. Concessions without reverse dates (permanent revenue loss)\n\n"
            "For EVERY finding, provide:\n"
            "- Citation: `[Source: <filename>, Row <number>]`\n"
            "- Why: Complete reasoning chain\n"
            "- Financial impact: Dollar amount at risk\n\n"
            "Format as a Markdown report with an executive summary, "
            "findings by severity, and specific dollar-amount recommendations."
        ),
        "🏢 Compliance & Policy Check": (
            "You are an internal auditor checking for policy compliance in property concessions. "
            "Verify the following policies:\n"
            "1. All concessions must have proper descriptions (flag generic ones)\n"
            "2. Move-in specials should not exceed one month's rent\n"
            "3. Employee unit allowances must be documented and limited\n"
            "4. No unit should have more than 2 active concessions\n"
            "5. All concessions over $500 must have notes explaining the reason\n"
            "6. Reversed concessions must have a matching original entry\n\n"
            "For EVERY finding, provide:\n"
            "- Citation: `[Source: <filename>, Row <number>]`\n"
            "- Policy violated: Which rule was broken\n"
            "- Why: Evidence and reasoning\n"
            "- Remediation: Specific corrective action\n\n"
            "Format as a Markdown report suitable for a compliance review meeting."
        ),
    }

    for label, template in templates.items():
        if st.button(label, key=f"template_{label}"):
            st.session_state.custom_prompt = template
            st.rerun()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    initialize_session_state()

    # Auto-load ResMan concession CSVs from data/ at startup (once per session)
    if not st.session_state["_resman_docs_loaded"]:
        with st.spinner("Loading concession data from data/ directory…"):
            st.session_state["resman_concession_docs"] = load_resman_csvs_from_data_dir()
        st.session_state["_resman_docs_loaded"] = True

    sidebar = render_new_sidebar()
    canonical_model: CanonicalModel = st.session_state.canonical_model
    audit_log: AuditLog = st.session_state.audit_log

    uploaded_files = sidebar["uploaded_files"]
    resman_docs = st.session_state.get("resman_concession_docs", [])

    # --- Audit status banner ---
    audit_result = st.session_state.get("audit_result")
    if resman_docs or uploaded_files:
        status_cols = st.columns([1, 1, 2])
        with status_cols[0]:
            st.success("✅ **Step 1 — Rule-Based Check:** Complete", icon="✅")
        with status_cols[1]:
            if audit_result:
                st.success("✅ **Step 2 — AI Audit:** Complete", icon="🤖")
            else:
                st.warning("⏳ **Step 2 — AI Audit:** Not yet run", icon="⏳")
        with status_cols[2]:
            if not audit_result:
                st.info(
                    "👈 Click **Run AI Audit** in the sidebar to get AI-powered findings and a full narrative report.",
                    icon="💡",
                )
    st.markdown("---")

    # Welcome screen — only when no uploaded files AND no auto-loaded concession data
    if not uploaded_files and not resman_docs:
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

    # Convert auto-loaded resman CSVs into ParsedDocument objects so the AI
    # engine can analyse them (resman_docs are (property_name, df) tuples).
    if resman_docs and not any(d.document_type == "concession" for d in parsed_docs):
        import pandas as pd
        for prop_name, rdf in resman_docs:
            parsed_docs.append(
                ParsedDocument(
                    file_name=f"{prop_name} Transaction List (Credits) - Feb 2026.csv",
                    file_type="csv",
                    raw_text=rdf.to_string(index=False),
                    dataframe=rdf,
                    document_type="concession",
                )
            )
        st.session_state.parsed_docs = parsed_docs

    # Detect content types
    doc_types = {d.document_type for d in parsed_docs}
    has_rent_roll = "rent_roll" in doc_types
    has_projection = "projection" in doc_types

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
            custom_prompt = st.session_state.get("custom_prompt")
            with st.spinner("🤖 Running AI audit agent… this may take a minute…"):
                try:
                    engine = LangGraphEngine(api_key=api_key)
                    result = engine.run(
                        canonical_model,
                        parsed_docs=parsed_docs,
                        custom_prompt=custom_prompt,
                    )
                    st.session_state.audit_result = result
                    st.session_state.audit_timestamp = datetime.now()
                    st.session_state.audit_prompt = result.prompt_used
                    st.success(
                        f"✅ Audit complete at {st.session_state.audit_timestamp.strftime('%Y-%m-%d %H:%M:%S')}"
                    )
                except ValueError as e:
                    st.error(str(e))
                except Exception as e:
                    st.error(f"Audit agent error: {e}")

    audit_result = st.session_state.get("audit_result")

    # --- Tab structure ---
    tabs_labels: List[str] = []
    if has_rent_roll:
        tabs_labels.append("📋 Rent Roll")
    if has_projection:
        tabs_labels.append("📊 Projections")
    tabs_labels += ["🔍 AI Findings", "📄 Full Report", "⚙️ Prompt Editor"]
    if parsed_docs:
        tabs_labels.append("🗂️ Raw Data")

    tabs = st.tabs(tabs_labels)
    tab_idx = 0

    if has_rent_roll:
        with tabs[tab_idx]:
            render_rent_roll_tab(rent_roll_doc)
        tab_idx += 1

    if has_projection:
        with tabs[tab_idx]:
            render_projection_tab(projection_doc)

            # --- Portfolio risk metrics ---
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
                        m1.metric(
                            "Monthly Leakage",
                            f"${filtered_df['Monthly_Projection'].abs().sum():,.2f}",
                        )
                        m2.metric(
                            "Units Tracked",
                            f"{len(filtered_df)}",
                        )
                        m3.metric(
                            "Total Portfolio Risk",
                            f"${filtered_df['Total_Lease_Loss'].abs().sum():,.2f}",
                        )
                except Exception as e:
                    st.warning(f"Could not compute portfolio risk metrics: {e}")

        tab_idx += 1

    with tabs[tab_idx]:
        render_findings_tab(audit_result, parsed_docs=parsed_docs)
    tab_idx += 1

    with tabs[tab_idx]:
        render_report_tab(audit_result, st.session_state.get("audit_timestamp"))
    tab_idx += 1

    # --- Prompt Editor tab ---
    with tabs[tab_idx]:
        _render_prompt_editor_tab(audit_result)
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

    st.markdown("---")
    st.caption(f"{settings.APP_TITLE} | {datetime.now().strftime('%Y-%m-%d %H:%M')}")


if __name__ == "__main__":
    main()
