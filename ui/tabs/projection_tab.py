"""
Transaction Projection tab renderer.
"""
import streamlit as st
import pandas as pd
import plotly.express as px
from typing import Optional

from ingestion.parsers import ParsedDocument
from utils.helpers import parse_month


def render_projection_tab(parsed_doc: Optional[ParsedDocument]) -> None:
    """Render the Transaction Projection tab."""
    st.subheader("📊 Transaction Projection")

    if parsed_doc is None or parsed_doc.dataframe is None or parsed_doc.dataframe.empty:
        st.info("No projection data available. Upload a projection file to see analysis.")
        return

    df = parsed_doc.dataframe.copy()

    # Identify month columns
    month_cols = [c for c in df.columns if parse_month(str(c)) is not None]

    if not month_cols:
        st.warning("Could not detect month columns in the projection file.")
        st.dataframe(df, use_container_width=True)
        return

    # --- Revenue trend line chart ---
    try:
        totals = {col: pd.to_numeric(df[col], errors="coerce").sum() for col in month_cols}
        trend_df = pd.DataFrame(
            {"Month": list(totals.keys()), "Total Charges": list(totals.values())}
        )
        fig = px.line(trend_df, x="Month", y="Total Charges", title="Revenue Trend by Month", markers=True)
        st.plotly_chart(fig, use_container_width=True)
    except Exception as e:
        st.warning(f"Could not render revenue trend: {e}")

    st.markdown("---")

    # --- Lease cliff heatmap ---
    st.subheader("Lease Cliff Heatmap (Leases Expiring per Month)")
    st.info("Upload a rent roll with lease end dates to see lease cliff heatmap.")

    st.markdown("---")

    # --- MTM fee tracker ---
    st.subheader("MTM Fee Tracker")
    if "Description" in df.columns or "description" in df.columns:
        desc_col = "Description" if "Description" in df.columns else "description"
        mtm_rows = df[df[desc_col].astype(str).str.lower().str.contains("mtm|month-to-month", na=False)]
        if not mtm_rows.empty:
            st.dataframe(mtm_rows[([desc_col] + month_cols)], use_container_width=True)
        else:
            st.info("No MTM fee rows detected.")
    else:
        st.info("No description column found to detect MTM fees.")

    st.markdown("---")

    # --- Concession credit trend ---
    st.subheader("Concession Credit Trend")
    if "Description" in df.columns or "description" in df.columns:
        desc_col = "Description" if "Description" in df.columns else "description"
        conc_rows = df[df[desc_col].astype(str).str.lower().str.contains("concession|credit|discount", na=False)]
        if not conc_rows.empty:
            conc_totals = {
                col: pd.to_numeric(conc_rows[col], errors="coerce").sum() for col in month_cols
            }
            conc_df = pd.DataFrame(
                {"Month": list(conc_totals.keys()), "Concession Credits": list(conc_totals.values())}
            )
            fig2 = px.bar(conc_df, x="Month", y="Concession Credits", title="Concession Credit Trend")
            st.plotly_chart(fig2, use_container_width=True)
        else:
            st.info("No concession rows detected.")
    else:
        st.info("No description column found to detect concessions.")
