"""
Concession Audit tab — full rule-based audit of ResMan Transaction CSVs.
"""
from __future__ import annotations

from typing import List, Optional

import pandas as pd
import plotly.express as px
import streamlit as st

from engine.concession_audit import (
    RULE_META,
    SEVERITY_COLORS,
    SEVERITY_ORDER,
    ConcessionAuditor,
    worst_severity,
)
from ingestion.parsers import ParsedDocument


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _row_color(flags: list[str]) -> str:
    sev = worst_severity(flags)
    if sev:
        return SEVERITY_COLORS[sev]
    return ""


def _style_row(row: pd.Series, color_map: dict[int, str]) -> list[str]:
    color = color_map.get(row.name, "")  # type: ignore[arg-type]
    if color:
        return [f"background-color: {color}"] * len(row)
    return [""] * len(row)


def _build_combined_df(
    resman_docs: list[tuple[str, pd.DataFrame]],
) -> tuple[pd.DataFrame, dict[str, pd.DataFrame]]:
    """Run ConcessionAuditor on each property and combine results."""
    combined_rows: list[pd.DataFrame] = []
    per_property: dict[str, pd.DataFrame] = {}

    for property_name, df in resman_docs:
        auditor = ConcessionAuditor(df, property_name)
        audited = auditor.run()
        audited.insert(0, "Property", property_name)
        per_property[property_name] = audited
        combined_rows.append(audited)

    if combined_rows:
        combined = pd.concat(combined_rows, ignore_index=True)
    else:
        combined = pd.DataFrame()

    return combined, per_property


def _display_cols(df: pd.DataFrame) -> list[str]:
    want = ["Property", "Date", "Unit", "Name", "Description", "Amount", "Reverse Date", "⚠️ Reason"]
    return [c for c in want if c in df.columns]


def _kpi_row(df: pd.DataFrame) -> None:
    flagged = df[df["_anomaly_reasons"] != ""]
    total_amount = df["Amount"].sum() if "Amount" in df.columns else 0.0
    amount_at_risk = flagged["Amount"].sum() if "Amount" in flagged.columns else 0.0
    critical_count = sum(
        1 for flags in df["_anomaly_flags"] if any("CRITICAL" in f for f in flags)
    )
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Total Transactions", f"{len(df):,}")
    c2.metric("Total Concession ($)", f"${total_amount:,.2f}")
    c3.metric("Flagged Rows", f"{len(flagged):,}")
    c4.metric("Amount at Risk ($)", f"${amount_at_risk:,.2f}")
    c5.metric("🔴 Critical Flags", f"{critical_count:,}")


def _anomaly_bar_chart(df: pd.DataFrame) -> None:
    rule_counts: list[dict] = []
    for flags in df["_anomaly_flags"]:
        seen: set[str] = set()
        for flag in flags:
            rule_id = flag.split("_")[0]
            if rule_id not in seen:
                seen.add(rule_id)
                label, severity = RULE_META.get(rule_id, (rule_id, "LOW"))
                rule_counts.append({"Rule": label, "Severity": severity})

    if not rule_counts:
        st.info("No anomalies detected.")
        return

    chart_df = pd.DataFrame(rule_counts)
    agg = chart_df.groupby(["Rule", "Severity"]).size().reset_index(name="Count")
    color_discrete_map = {sev: SEVERITY_COLORS[sev] for sev in SEVERITY_ORDER}
    fig = px.bar(
        agg,
        x="Count",
        y="Rule",
        color="Severity",
        orientation="h",
        title="Anomaly Flag Count by Rule",
        color_discrete_map=color_discrete_map,
        category_orders={"Severity": SEVERITY_ORDER},
    )
    fig.update_layout(yaxis={"categoryorder": "total ascending"}, showlegend=True)
    st.plotly_chart(fig, use_container_width=True)


def _highlighted_table(df: pd.DataFrame) -> None:
    display = df.copy()
    display["⚠️ Reason"] = display["_anomaly_reasons"]
    display_cols = _display_cols(display)
    display = display[display_cols].copy()

    color_map: dict[int, str] = {}
    for i, flags in enumerate(df["_anomaly_flags"]):
        c = _row_color(flags)
        if c:
            color_map[i] = c

    styled = display.style.apply(_style_row, color_map=color_map, axis=1)
    st.dataframe(styled, use_container_width=True, height=500)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def render_concession_tab(
    parsed_docs: Optional[List[ParsedDocument]],
    resman_docs: Optional[list[tuple[str, pd.DataFrame]]] = None,
) -> None:
    """
    Render the Concession Audit tab.

    Parameters
    ----------
    parsed_docs:
        Documents from user-uploaded files (legacy, kept for backward compat).
    resman_docs:
        List of ``(property_name, dataframe)`` tuples auto-loaded from
        ``data/``.
    """
    st.subheader("🏠 Concession Audit")

    effective_resman: list[tuple[str, pd.DataFrame]] = list(resman_docs or [])

    if not effective_resman:
        st.info(
            "ℹ️ No ResMan Transaction List CSVs were found in the `data/` directory. "
            "Place files matching `*Transaction List (Credits)*.csv` in the `data/` folder "
            "and restart the app."
        )
        return

    # -------------------------------------------------------------------
    # Build audited DataFrames
    # -------------------------------------------------------------------
    combined_df, per_property = _build_combined_df(effective_resman)

    if combined_df.empty:
        st.warning("No transaction rows found across all loaded files.")
        return

    # -------------------------------------------------------------------
    # Severity legend
    # -------------------------------------------------------------------
    st.markdown(
        "<div style='margin-bottom:8px'>"
        "<b>Severity legend:</b>&nbsp;&nbsp;"
        "<span style='background:#FF4B4B;padding:2px 8px;border-radius:4px;color:white'>🔴 Critical</span>&nbsp;"
        "<span style='background:#FF8C00;padding:2px 8px;border-radius:4px;color:white'>🟠 High</span>&nbsp;"
        "<span style='background:#FFD700;padding:2px 8px;border-radius:4px'>🟡 Medium</span>&nbsp;"
        "<span style='background:#90EE90;padding:2px 8px;border-radius:4px'>🟢 Low</span>"
        "</div>",
        unsafe_allow_html=True,
    )

    # -------------------------------------------------------------------
    # Property selector
    # -------------------------------------------------------------------
    property_names = sorted(per_property.keys())
    selected_property = st.selectbox(
        "Filter by property",
        options=["All Properties"] + property_names,
        index=0,
    )

    view_df = combined_df if selected_property == "All Properties" else per_property[selected_property]

    # -------------------------------------------------------------------
    # KPI row
    # -------------------------------------------------------------------
    _kpi_row(view_df)
    st.markdown("---")

    # -------------------------------------------------------------------
    # Anomaly summary bar chart
    # -------------------------------------------------------------------
    st.subheader("📊 Anomaly Summary")
    _anomaly_bar_chart(view_df)
    st.markdown("---")

    # -------------------------------------------------------------------
    # Highlighted transaction table
    # -------------------------------------------------------------------
    st.subheader("📋 Transaction Table")
    st.caption(
        "Rows are colour-coded by the worst severity flag. "
        "The **⚠️ Reason** column shows the audit finding(s) for each row."
    )
    _highlighted_table(view_df)

    # Download flagged rows only
    flagged_df = view_df[view_df["_anomaly_reasons"] != ""].copy()
    flagged_df["⚠️ Reason"] = flagged_df["_anomaly_reasons"]
    download_cols = _display_cols(flagged_df)
    if not flagged_df.empty:
        csv_bytes = flagged_df[download_cols].to_csv(index=False).encode()
        st.download_button(
            label="⬇️ Download flagged rows as CSV",
            data=csv_bytes,
            file_name="concession_audit_flagged.csv",
            mime="text/csv",
        )

    st.markdown("---")

    # -------------------------------------------------------------------
    # Per-property breakdown
    # -------------------------------------------------------------------
    st.subheader("🏘️ Per-Property Breakdown")
    for prop_name, prop_df in sorted(per_property.items()):
        prop_total = prop_df["Amount"].sum() if "Amount" in prop_df.columns else 0.0
        prop_flagged = int((prop_df["_anomaly_reasons"] != "").sum())
        with st.expander(
            f"{prop_name}  —  {len(prop_df)} transactions  |  "
            f"Total: ${prop_total:,.2f}  |  Flagged: {prop_flagged}",
            expanded=False,
        ):
            mini = prop_df.copy()
            mini["⚠️ Reason"] = mini["_anomaly_reasons"]
            mini_cols = _display_cols(mini)
            st.dataframe(mini[mini_cols], use_container_width=True)
