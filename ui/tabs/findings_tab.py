"""
AI Findings tab renderer.
"""
import streamlit as st
import pandas as pd
from typing import Optional
import io

from agents.audit_agent import AuditResult
from ingestion.parsers import ParsedDocument
from utils.helpers import parse_month, find_property_total_row


def _render_summary_banner(parsed_docs: list) -> None:
    """Show a quick-glance banner with concession, MTM, and cliff counts."""
    concession_units = 0
    mtm_units = 0
    cliff_months = 0

    for doc in parsed_docs:
        if not isinstance(doc, ParsedDocument):
            continue
        df = doc.dataframe
        if df is None or df.empty:
            continue

        # Find a text column for category/description detection
        text_col = None
        for candidate in ("Category", "category", "Description", "description"):
            if candidate in df.columns:
                text_col = candidate
                break
        if text_col is None:
            continue

        lower_vals = df[text_col].astype(str).str.lower()

        concession_units += int(lower_vals.str.contains("concession", na=False).sum())
        mtm_units += int(
            lower_vals.str.contains("mtm|month-to-month|month to month", na=False).sum()
        )

        # Revenue cliff: ≥10% MoM drop in Property Total row
        month_cols = [c for c in df.columns if parse_month(str(c)) is not None]
        if month_cols:
            total_row = find_property_total_row(df)
            if total_row is not None and not total_row.empty:
                prev = None
                for mc in month_cols:
                    cur = pd.to_numeric(total_row[mc], errors="coerce").sum()
                    if prev is not None and prev > 0 and cur < prev * 0.9:
                        cliff_months += 1
                    prev = cur

    if concession_units or mtm_units or cliff_months:
        col1, col2, col3 = st.columns(3)
        col1.metric("🎟️ Concession Rows", concession_units)
        col2.metric("📅 MTM Rows", mtm_units)
        col3.metric("📉 Revenue Cliff Months", cliff_months)
        st.markdown("---")


def render_findings_tab(
    audit_result: Optional[AuditResult],
    parsed_docs: Optional[list] = None,
) -> None:
    """Render the AI Findings tab."""
    st.subheader("🔍 AI Findings")

    # --- Summary banner from parsed projection data ---
    if parsed_docs:
        _render_summary_banner(parsed_docs)

    if audit_result is None:
        st.warning(
            "🤖 **AI audit has not been run yet.**\n\n"
            "The Concession Check tab shows rule-based flags that run automatically. "
            "To get AI-powered findings (deeper pattern analysis, narrative explanations, "
            "and severity scoring), click **🚀 Run AI Audit** in the sidebar.\n\n"
            "You'll need an OpenAI API key to proceed.",
            icon="⏳",
        )
        return

    counts = audit_result.severity_counts
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("🔴 Critical", counts.get("critical", 0))
    col2.metric("🟠 High", counts.get("high", 0))
    col3.metric("🟡 Medium", counts.get("medium", 0))
    col4.metric("🟢 Low", counts.get("low", 0))

    st.markdown("---")

    anomalies = audit_result.anomalies
    if not anomalies:
        st.success("No structured anomalies extracted. See Full Report tab for narrative findings.")
        return

    df = pd.DataFrame(anomalies)

    # Filters
    col_a, col_b, col_c = st.columns(3)
    with col_a:
        sev_filter = st.multiselect(
            "Filter by Severity",
            options=["critical", "high", "medium", "low"],
            default=["critical", "high", "medium", "low"],
        )
    with col_b:
        if "unit" in df.columns:
            unit_filter = st.multiselect("Filter by Unit", options=sorted(df["unit"].unique()), default=[])
        else:
            unit_filter = []
    with col_c:
        if "description" in df.columns:
            type_filter = st.text_input("Filter by keyword", value="")
        else:
            type_filter = ""

    filtered = df[df["severity"].isin(sev_filter)] if sev_filter else df
    if unit_filter and "unit" in filtered.columns:
        filtered = filtered[filtered["unit"].isin(unit_filter)]
    if type_filter and "description" in filtered.columns:
        filtered = filtered[filtered["description"].str.contains(type_filter, case=False, na=False)]

    st.dataframe(filtered, use_container_width=True)

    # Download button
    csv_buf = io.StringIO()
    filtered.to_csv(csv_buf, index=False)
    st.download_button(
        "⬇️ Download Anomalies as CSV",
        data=csv_buf.getvalue(),
        file_name="audit_anomalies.csv",
        mime="text/csv",
    )
