"""
AI Findings tab renderer — per-CSV sub-tabs with expandable detail.
"""
import streamlit as st
import pandas as pd
from typing import Optional
import io

from agents.audit_agent import AuditResult
from ingestion.parsers import ParsedDocument


def _render_severity_badge(sev: str) -> str:
    """Return an emoji badge for severity level."""
    return {
        "critical": "🔴",
        "high": "🟠",
        "medium": "🟡",
        "low": "🟢",
    }.get(sev, "⚪")


def _render_overview_metrics(anomalies: list[dict]) -> None:
    """Show top-level severity counts."""
    counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for a in anomalies:
        sev = a.get("severity", "low")
        counts[sev] = counts.get(sev, 0) + 1
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("🔴 Critical", counts["critical"])
    col2.metric("🟠 High", counts["high"])
    col3.metric("🟡 Medium", counts["medium"])
    col4.metric("🟢 Low", counts["low"])


def _make_citation(row_dict: dict) -> str:
    src = str(row_dict.get("source", "")).strip()
    r = str(row_dict.get("row", "")).strip()
    if src and r:
        return f"{src}, Row {r}"
    if src:
        return src
    return ""


def _render_findings_for_source(
    anomalies: list[dict],
    key_prefix: str = "",
) -> None:
    """Render findings for a single source file with expandable detail."""
    if not anomalies:
        st.info("No findings for this property.")
        return

    # Summary metrics for this source
    _render_overview_metrics(anomalies)
    st.markdown("---")

    # Show each finding as an expandable card
    for i, finding in enumerate(anomalies):
        sev = finding.get("severity", "low")
        badge = _render_severity_badge(sev)
        desc = finding.get("description", "No description")
        citation = _make_citation(finding)
        unit = finding.get("unit", "")
        reasoning = finding.get("reasoning", "")
        evidence = finding.get("evidence", [])

        # Short summary line for the expander header
        header = f"{badge} **{sev.upper()}** — {desc[:120]}"
        if unit:
            header += f" (Unit {unit})"

        with st.expander(header, expanded=(sev in ("critical", "high") and i < 5)):
            col_a, col_b = st.columns([3, 1])
            with col_a:
                st.markdown(f"**Description:** {desc}")
                if citation:
                    st.markdown(f"**📎 Citation:** `{citation}`")
                if unit:
                    st.markdown(f"**Affected Units:** {unit}")
            with col_b:
                st.markdown(f"**Severity:** {badge} {sev.upper()}")

            if reasoning:
                st.markdown("---")
                st.markdown(f"**💭 Reasoning:** {reasoning}")

            # Show row-level evidence if available (from deterministic findings)
            if evidence:
                st.markdown("---")
                st.markdown("**📋 Row-Level Evidence:**")
                ev_df = pd.DataFrame(evidence)
                st.dataframe(ev_df, use_container_width=True, hide_index=True)


def _group_by_source(anomalies: list[dict]) -> dict[str, list[dict]]:
    """Group anomalies by source file."""
    groups: dict[str, list[dict]] = {}
    for a in anomalies:
        src = a.get("source", "").strip()
        if not src:
            src = "Uncategorized"
        groups.setdefault(src, []).append(a)
    return groups


def render_findings_tab(
    audit_result: Optional[AuditResult],
    parsed_docs: Optional[list] = None,
) -> None:
    """Render the AI Findings tab with per-CSV sub-tabs."""
    st.subheader("🔍 AI Findings")

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

    anomalies = audit_result.anomalies
    if not anomalies:
        st.success("No anomalies found. See Full Report tab for the complete narrative.")
        return

    # --- Overall metrics ---
    _render_overview_metrics(anomalies)
    st.markdown("---")

    # --- Group findings by source CSV ---
    grouped = _group_by_source(anomalies)
    source_names = list(grouped.keys())

    # Build sub-tab labels: "📊 All" + one per source file
    sub_tab_labels = ["📊 All Properties"]
    for src in source_names:
        # Shorten the label to property abbreviation
        short = src.replace(" Transaction List (Credits) - Feb 2026.csv", "").strip()
        count = len(grouped[src])
        sub_tab_labels.append(f"🏢 {short} ({count})")

    sub_tabs = st.tabs(sub_tab_labels)

    # --- All Properties overview ---
    with sub_tabs[0]:
        st.markdown("### All Properties — Combined Findings")

        # Summary table
        summary_rows = []
        for src in source_names:
            items = grouped[src]
            short = src.replace(" Transaction List (Credits) - Feb 2026.csv", "").strip()
            counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
            for a in items:
                counts[a.get("severity", "low")] += 1
            summary_rows.append({
                "Property": short,
                "🔴 Critical": counts["critical"],
                "🟠 High": counts["high"],
                "🟡 Medium": counts["medium"],
                "🟢 Low": counts["low"],
                "Total": len(items),
            })
        if summary_rows:
            st.dataframe(pd.DataFrame(summary_rows), use_container_width=True, hide_index=True)

        st.markdown("---")

        # All findings — filterable
        sev_filter = st.multiselect(
            "Filter by Severity",
            options=["critical", "high", "medium", "low"],
            default=["critical", "high", "medium", "low"],
            key="all_sev_filter",
        )
        filtered = [a for a in anomalies if a.get("severity", "low") in sev_filter]
        _render_findings_for_source(filtered, key_prefix="all")

        # Download
        if filtered:
            dl_df = pd.DataFrame(filtered)
            csv_buf = io.StringIO()
            dl_df.to_csv(csv_buf, index=False)
            st.download_button(
                "⬇️ Download All Findings as CSV",
                data=csv_buf.getvalue(),
                file_name="audit_findings_all.csv",
                mime="text/csv",
            )

    # --- Per-source sub-tabs ---
    for idx, src in enumerate(source_names):
        with sub_tabs[idx + 1]:
            short = src.replace(" Transaction List (Credits) - Feb 2026.csv", "").strip()
            st.markdown(f"### {short}")
            st.caption(f"Source: `{src}`")

            items = grouped[src]

            sev_filter = st.multiselect(
                "Filter by Severity",
                options=["critical", "high", "medium", "low"],
                default=["critical", "high", "medium", "low"],
                key=f"sev_{idx}",
            )
            filtered = [a for a in items if a.get("severity", "low") in sev_filter]
            _render_findings_for_source(filtered, key_prefix=f"src_{idx}")

            # Download
            if filtered:
                dl_df = pd.DataFrame(filtered)
                csv_buf = io.StringIO()
                dl_df.to_csv(csv_buf, index=False)
                st.download_button(
                    f"⬇️ Download {short} Findings as CSV",
                    data=csv_buf.getvalue(),
                    file_name=f"audit_findings_{short}.csv",
                    mime="text/csv",
                    key=f"dl_{idx}",
                )
