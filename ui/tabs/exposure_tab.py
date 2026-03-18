"""
Exposure Drilldowns tab — by_property / by_rule / by_risk breakdowns + manager exposure.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from config.fee_schedules import RISK_CRITICAL, RISK_HIGH, RISK_MEDIUM
from utils.risk_styles import styled_df


def render_exposure_tab(
    exposure: dict,
    override_log: pd.DataFrame,
) -> None:
    """Renders by_property / by_rule / by_risk drilldowns + manager exposure."""
    st.header("Exposure Drilldowns")

    by_prop = exposure.get("by_property", pd.DataFrame())
    by_rule = exposure.get("by_rule", pd.DataFrame())
    by_risk = exposure.get("by_risk", pd.DataFrame())

    tabs = st.tabs(
        ["By Property", "By Rule", "By Risk Level", "Manager Exposure"]
    )

    with tabs[0]:
        st.subheader("Exposure by Property")
        if by_prop.empty:
            st.info("No data.")
        else:
            st.dataframe(styled_df(by_prop), use_container_width=True, hide_index=True)
            st.caption(
                f"Total: **${by_prop['Total_Exposure'].sum():,.2f}** across "
                f"{by_prop['Property'].nunique()} properties"
            )

    with tabs[1]:
        st.subheader("Exposure by Rule")
        if by_rule.empty:
            st.info("No data.")
        else:
            st.dataframe(styled_df(by_rule), use_container_width=True, hide_index=True)

    with tabs[2]:
        st.subheader("Exposure by Risk Level")
        if by_risk.empty:
            st.info("No data.")
        else:
            cols = st.columns(3)
            for idx, risk in enumerate([RISK_CRITICAL, RISK_HIGH, RISK_MEDIUM]):
                row = by_risk[by_risk["Risk_Level"] == risk]
                if not row.empty:
                    count = int(row["Count"].iloc[0])
                    exposure_amt = float(row["Total_Exposure"].iloc[0])
                else:
                    count, exposure_amt = 0, 0.0
                cols[idx].metric(f"{risk} Flags", count)
                cols[idx].metric(f"{risk} Exposure", f"${exposure_amt:,.2f}")

            st.divider()
            st.dataframe(by_risk, use_container_width=True, hide_index=True)

    with tabs[3]:
        st.subheader("Manager Revenue Impact")
        if override_log is None or override_log.empty:
            st.info("No override data available.")
        else:
            mgr_exp = (
                override_log.groupby(["Property", "Manager_Login"])
                .agg(Events=("Event_Type", "count"), Revenue_Impact=("Revenue_Impact", "sum"))
                .reset_index()
                .sort_values("Revenue_Impact", ascending=True)
            )
            st.dataframe(mgr_exp, use_container_width=True, hide_index=True)
            st.caption(
                f"Total revenue impact: **${override_log['Revenue_Impact'].sum():,.2f}**"
            )
