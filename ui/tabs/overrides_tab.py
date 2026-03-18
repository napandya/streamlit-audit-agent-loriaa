"""
Manager Overrides tab — leaderboard + filterable raw override log.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st


def render_overrides_tab(
    manager_ranking: pd.DataFrame,
    override_log: pd.DataFrame,
) -> None:
    """Renders manager leaderboard + filterable raw override log."""
    st.header("Manager Override Audit")
    st.markdown(
        "Tracks every manual ledger edit from the **Edited Transactions by User** report. "
        "Rankings are by total revenue impact (most negative = greatest risk)."
    )

    if manager_ranking.empty:
        st.info("ℹ️ No edited transaction data found. Place CSV files in `data/edits/`.")
        return

    st.subheader("Manager Leaderboard")
    st.dataframe(manager_ranking, use_container_width=True, hide_index=True)

    col1, col2, col3 = st.columns(3)
    col1.metric("Total Events", f"{manager_ranking['Total_Events'].sum():,}")
    col2.metric("Total Reversals", f"{manager_ranking['Reversals'].sum():,}")
    col3.metric(
        "Total Revenue Impact",
        f"${manager_ranking['Total_Impact'].sum():,.2f}",
    )

    if override_log.empty:
        return

    st.divider()
    st.subheader("Raw Override Log")

    filter_cols = st.columns(3)
    with filter_cols[0]:
        props = ["All"] + sorted(override_log["Property"].dropna().unique().tolist())
        prop_sel = st.selectbox("Property", props, key="ovr_prop")
    with filter_cols[1]:
        mgrs = ["All"] + sorted(override_log["Manager_Login"].dropna().unique().tolist())
        mgr_sel = st.selectbox("Manager", mgrs, key="ovr_mgr")
    with filter_cols[2]:
        evt_types = ["All"] + sorted(override_log["Event_Type"].dropna().unique().tolist())
        evt_sel = st.selectbox("Event Type", evt_types, key="ovr_evt")

    view = override_log.copy()
    if prop_sel != "All":
        view = view[view["Property"] == prop_sel]
    if mgr_sel != "All":
        view = view[view["Manager_Login"] == mgr_sel]
    if evt_sel != "All":
        view = view[view["Event_Type"] == evt_sel]

    st.dataframe(view, use_container_width=True, hide_index=True)
    st.caption(f"{len(view):,} records shown")
