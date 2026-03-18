"""
Shared risk-level styling utilities for Streamlit DataFrames.

Centralises the ``RISK_COLORS`` palette, the ``color_risk`` cell-styler,
and the ``styled_df`` helper so that every UI tab uses identical visual
treatment without duplicating code.
"""
from __future__ import annotations

import pandas as pd

from config.fee_schedules import RISK_CRITICAL, RISK_HIGH, RISK_MEDIUM

# ---------------------------------------------------------------------------
# Colour palette
# ---------------------------------------------------------------------------
RISK_COLORS: dict[str, str] = {
    RISK_CRITICAL: "#FF4B4B",
    RISK_HIGH: "#FFA500",
    RISK_MEDIUM: "#FFD700",
}


# ---------------------------------------------------------------------------
# Cell-level styler
# ---------------------------------------------------------------------------
def color_risk(val: str) -> str:
    """Return a CSS background-color string for a Risk_Level cell value."""
    color = RISK_COLORS.get(val, "#FFFFFF")
    return f"background-color: {color}; color: black; font-weight: bold;"


# ---------------------------------------------------------------------------
# DataFrame helper
# ---------------------------------------------------------------------------
def styled_df(df: pd.DataFrame, risk_col: str = "Risk_Level") -> object:
    """
    Apply ``color_risk`` to *risk_col* and return the Styler object.

    Returns the plain DataFrame (unstyled) if it is empty or the column is
    absent, so callers never have to guard against KeyErrors.
    """
    if df.empty or risk_col not in df.columns:
        return df
    return df.style.map(color_risk, subset=[risk_col])
