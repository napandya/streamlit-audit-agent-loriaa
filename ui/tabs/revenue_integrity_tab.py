"""
Revenue Integrity tab — Daniel's 2-stage engine results.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from config.fee_schedules import RISK_CRITICAL, RISK_HIGH, RISK_MEDIUM

RISK_COLORS = {
    RISK_CRITICAL: "#FF4B4B",
    RISK_HIGH: "#FFA500",
    RISK_MEDIUM: "#FFD700",
}

STAGE1_RULES = {
    "Missing Standard Charge",
    "Major Charge Amount Variance",
    "Minor Charge Amount Variance",
    "Recurring Concession >$700",
    "Concession >$500 for 2+ Months",
    "Concession No Expiration",
    "Post-Term Credit",
}
STAGE2_RULES = {
    "Negative Net Rent",
    "$0 Net Rent (Recent Move-in)",
    "$0 Net Rent (Not Recent)",
    "Manual Posting Without Setup",
    "Invalid Credit Code",
    "Posted vs Recurring Mismatch",
    "Misc Tenant Credit",
}


def _color_risk(val: str) -> str:
    color = RISK_COLORS.get(val, "#FFFFFF")
    return f"background-color: {color}; color: black; font-weight: bold;"


def _styled(df: pd.DataFrame) -> object:
    if df.empty or "Risk_Level" not in df.columns:
        return df
    return df.style.applymap(_color_risk, subset=["Risk_Level"])


def _stage_section(flags: pd.DataFrame, title: str) -> None:
    if flags.empty:
        st.success(f"✅ No {title} issues found.")
        return

    rule_summary = (
        flags.groupby(["Rule", "Risk_Level"])
        .agg(Count=("Rule", "count"), Exposure=("Amount_Impact", "sum"))
        .reset_index()
        .sort_values("Exposure", ascending=False)
    )
    st.subheader("Rule Summary")
    st.dataframe(_styled(rule_summary), use_container_width=True, hide_index=True)

    st.divider()
    st.subheader("Unit-Level Flags")
    st.dataframe(_styled(flags), use_container_width=True, hide_index=True)
    st.caption(f"Total Exposure: **${flags['Amount_Impact'].sum():,.2f}** | {len(flags):,} flags")


def render_revenue_integrity_tab(daniels_flags: pd.DataFrame) -> None:
    """Renders Daniel's 2-stage engine results with Stage 1 / Stage 2 sub-tabs."""
    st.header("Revenue Integrity Audit — Daniel's 2-Stage Engine")
    st.markdown(
        "**Stage 1** validates what *should* post each month (Recurring Transaction Projection). "
        "**Stage 2** validates what *is* posted (Rent Roll)."
    )

    s1_tab, s2_tab = st.tabs(
        ["Stage 1 — Recurring Projection", "Stage 2 — Posted Rent Roll"]
    )

    stage1_flags = (
        daniels_flags[daniels_flags["Rule"].isin(STAGE1_RULES)]
        if not daniels_flags.empty
        else pd.DataFrame()
    )
    stage2_flags = (
        daniels_flags[daniels_flags["Rule"].isin(STAGE2_RULES)]
        if not daniels_flags.empty
        else pd.DataFrame()
    )

    with s1_tab:
        st.markdown("*What should post every month vs what is configured.*")
        _stage_section(stage1_flags, "Stage 1 (Recurring Projection)")

    with s2_tab:
        st.markdown("*What is actually posted on the Rent Roll.*")
        _stage_section(stage2_flags, "Stage 2 (Posted Rent Roll)")
