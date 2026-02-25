"""
Concession Audit tab renderer.
"""
import streamlit as st
import pandas as pd
import plotly.express as px
from typing import List, Optional

from ingestion.parsers import ParsedDocument


def render_concession_tab(parsed_docs: Optional[List[ParsedDocument]]) -> None:
    """Render the Concession Audit tab."""
    st.subheader("💰 Concession Audit")

    if not parsed_docs:
        st.info("No documents uploaded. Upload files to see concession analysis.")
        return

    # Collect concession line items from all documents
    all_concession_rows: List[dict] = []

    for doc in parsed_docs:
        if doc.dataframe is None or doc.dataframe.empty:
            continue
        df = doc.dataframe
        # Look for description/amount columns
        desc_col = next(
            (c for c in df.columns if str(c).lower() in ["description", "desc", "charge type", "type"]),
            None,
        )
        amt_col = next(
            (c for c in df.columns if str(c).lower() in ["amount", "charge", "total", "value"]),
            None,
        )
        if desc_col is None:
            continue

        mask = df[desc_col].astype(str).str.lower().str.contains(
            "concession|discount|credit|allowance|special", na=False
        )
        for _, row in df[mask].iterrows():
            entry = {"Source File": doc.file_name, "Description": str(row[desc_col])}
            if amt_col:
                entry["Amount"] = row[amt_col]
                try:
                    amt = float(str(row[amt_col]).replace("$", "").replace(",", ""))
                    entry["Amount (num)"] = amt
                except Exception:
                    entry["Amount (num)"] = 0.0
            all_concession_rows.append(entry)

    if not all_concession_rows:
        st.info("No concession line items found in the uploaded documents.")
        return

    conc_df = pd.DataFrame(all_concession_rows)

    # Flag $999 special
    if "Amount (num)" in conc_df.columns:
        conc_df["⚠️ $999 Special"] = conc_df["Amount (num)"].apply(
            lambda x: "⚠️ YES" if x <= -999 or (0 < x <= 999) else ""
        )

    st.dataframe(conc_df.drop(columns=["Amount (num)"], errors="ignore"), use_container_width=True)

    st.markdown("---")

    # --- Pie chart: concession types ---
    if "Description" in conc_df.columns:
        type_counts = conc_df["Description"].value_counts().reset_index()
        type_counts.columns = ["Concession Type", "Count"]
        fig = px.pie(type_counts, names="Concession Type", values="Count", title="Concession Types Breakdown")
        st.plotly_chart(fig, use_container_width=True)
