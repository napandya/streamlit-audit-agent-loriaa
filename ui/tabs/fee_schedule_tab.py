"""
Fee Schedule Check tab — violation summary + unit-level detail + fee schedule reference.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from config.fee_schedules import PROPERTY_FEE_SCHEDULE, RISK_CRITICAL, RISK_HIGH, RISK_MEDIUM
from utils.risk_styles import styled_df


def render_fee_schedule_tab(fee_flags: pd.DataFrame) -> None:
    """Renders fee schedule violation summary + unit-level detail + reference table."""
    st.header("Fee Schedule Check")
    st.markdown(
        "Validates each unit's recurring charges against the **official per-property "
        "fee schedules** (Daniel Twito, March 2026). "
        "Flags any charge with a variance ≥ $1.00 from the scheduled amount."
    )

    if fee_flags is None or fee_flags.empty:
        st.success("✅ No fee schedule violations detected.")
    else:
        # Summary by property
        summary = (
            fee_flags.groupby(["Property", "Risk_Level"])
            .agg(Violations=("Rule", "count"), Total_Variance=("Amount_Impact", "sum"))
            .reset_index()
            .sort_values("Total_Variance", ascending=False)
        )

        col1, col2 = st.columns(2)
        col1.metric("Total Violations", len(fee_flags))
        col2.metric(
            "Total Fee Variance",
            f"${fee_flags['Amount_Impact'].sum():,.2f}",
        )

        st.divider()
        st.subheader("Violations by Property")
        st.dataframe(styled_df(summary), use_container_width=True, hide_index=True)

        st.divider()
        st.subheader("Unit-Level Violations")
        st.dataframe(styled_df(fee_flags), use_container_width=True, hide_index=True)
        st.caption(f"{len(fee_flags):,} violations | "
                   f"Total Variance: **${fee_flags['Amount_Impact'].sum():,.2f}**")

    # -------------------------------------------------------------------------
    # Fee Schedule Reference Table
    # -------------------------------------------------------------------------
    st.divider()
    st.subheader("Fee Schedule Reference")
    st.caption("Source: Daniel Twito's fee sheets (March 2026)")

    ref_rows = []
    for prop, fees in PROPERTY_FEE_SCHEDULE.items():
        for fee in fees:
            ref_rows.append({
                "Property": prop,
                "Fee Name": fee["name"],
                "Monthly Amount": f"${fee['amount']:.2f}",
                "Type": "Optional" if fee["optional"] else "Standard",
            })

    if ref_rows:
        ref_df = pd.DataFrame(ref_rows)
        prop_options = ["All Properties"] + sorted(ref_df["Property"].unique().tolist())
        selected = st.selectbox("Filter reference by property", prop_options)
        view = ref_df if selected == "All Properties" else ref_df[ref_df["Property"] == selected]
        st.dataframe(view, use_container_width=True, hide_index=True)
