"""
AI Findings tab renderer.
"""
import streamlit as st
import pandas as pd
from typing import Optional
import io

from agents.audit_agent import AuditResult


def render_findings_tab(audit_result: Optional[AuditResult]) -> None:
    """Render the AI Findings tab."""
    st.subheader("🔍 AI Findings")

    if audit_result is None:
        st.info("Run the audit to see AI-generated findings.")
        return

    counts = audit_result.severity_counts
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("🔴 Critical", counts.get("critical", 0))
    col2.metric("🟠 High", counts.get("high", 0))
    col3.metric("🟡 Medium", counts.get("medium", 0))
    col4.metric("🟢 Low", counts.get("low", 0))

    st.markdown("---")

    anomalies = audit_result.anomalies

    # --- Summary banner for key risk categories ---
    if anomalies:
        df_all = pd.DataFrame(anomalies)
        if "category" in df_all.columns:
            conc_count = int((df_all["category"] == "Concession").sum())
            mtm_count = int((df_all["category"] == "MTM").sum())
            cliff_count = int((df_all["category"] == "Lease Cliff").sum())
            if conc_count or mtm_count or cliff_count:
                st.info(
                    f"📊 **Risk Summary** — "
                    f"🏷️ Concession units: **{conc_count}** | "
                    f"🔄 MTM tenants: **{mtm_count}** | "
                    f"📉 Revenue cliff months: **{cliff_count}**"
                )

    st.markdown("---")

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
