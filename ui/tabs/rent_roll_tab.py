"""
Rent Roll Audit tab renderer.
"""
import streamlit as st
import pandas as pd
import plotly.express as px
from typing import Optional

from ingestion.parsers import ParsedDocument
from utils.data_processor import DataProcessor


_STATUS_BADGE = {
    "UE": "🔴",
    "NTV": "🟡",
    "MTM": "🟠",
    "C": "🟢",
    "VACANT": "⚪",
}


def _badge(status: str) -> str:
    return _STATUS_BADGE.get(str(status).upper(), "⬜") + " " + status


def render_rent_roll_tab(parsed_doc: Optional[ParsedDocument]) -> None:
    """Render the Rent Roll Audit tab."""
    st.subheader("📋 Rent Roll Audit")

    if parsed_doc is None or parsed_doc.dataframe is None or parsed_doc.dataframe.empty:
        st.info("No rent roll data available. Upload a rent roll file to see analysis.")
        return

    processor = DataProcessor()
    df = processor.normalize_columns(parsed_doc.dataframe.copy())

    # --- KPI row ---
    total = len(df)
    vacant_mask = df.get("status", pd.Series()).astype(str).str.upper().isin(["VACANT", "V"])
    ue_mask = df.get("status", pd.Series()).astype(str).str.upper() == "UE"
    ntv_mask = df.get("status", pd.Series()).astype(str).str.upper() == "NTV"
    mtm_mask = df.get("status", pd.Series()).astype(str).str.upper() == "MTM"

    vacant_count = int(vacant_mask.sum())
    ue_count = int(ue_mask.sum())
    ntv_count = int(ntv_mask.sum())
    mtm_count = int(mtm_mask.sum())
    occupied = total - vacant_count
    occ_pct = (occupied / total * 100) if total else 0

    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Total Units", total)
    col2.metric("Occupied %", f"{occ_pct:.1f}%")
    col3.metric("⚪ Vacant", vacant_count)
    col4.metric("🔴 Under Eviction", ue_count)
    col5.metric("🟡 NTV", ntv_count)

    st.markdown("---")

    # --- Display table with status badges ---
    display_df = df.copy()
    if "status" in display_df.columns:
        display_df["Status Badge"] = display_df["status"].apply(_badge)

    # Highlight large balances
    if "balance" in display_df.columns:
        display_df["_balance_num"] = pd.to_numeric(display_df["balance"], errors="coerce").fillna(0)
        display_df["⚠️ High Balance"] = display_df["_balance_num"].apply(
            lambda x: "⚠️ YES" if x > 1000 else ""
        )

    st.dataframe(display_df, use_container_width=True)

    st.markdown("---")

    # --- Occupancy by unit type chart ---
    if "Type" in df.columns or "type" in df.columns:
        type_col = "Type" if "Type" in df.columns else "type"
        status_col = "status" if "status" in df.columns else None
        if status_col:
            chart_df = df.groupby(type_col)[status_col].value_counts().reset_index(name="count")
            fig = px.bar(
                chart_df,
                x=type_col,
                y="count",
                color=status_col,
                title="Occupancy by Unit Type",
                barmode="stack",
            )
            st.plotly_chart(fig, use_container_width=True)
