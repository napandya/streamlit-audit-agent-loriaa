"""
Audit engine for recurring transaction and lease loss analysis.

Processes projection and rent roll data to compute Monthly_Projection,
Months_Remaining, and Total_Lease_Loss metrics.
"""

import re
from datetime import datetime
from typing import Optional

import pandas as pd


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------

def resilient_read(value) -> float:
    """Parse a string or numeric value to float, returning 0.0 on failure."""
    try:
        if pd.isna(value):
            return 0.0
        cleaned = re.sub(r"[,$\s]", "", str(value))
        return float(cleaned)
    except (ValueError, TypeError):
        return 0.0


def _find_header_row(raw_rows: list, keywords: list) -> int:
    """
    Scan raw CSV rows to find the first row that contains all expected keywords.

    Returns the row index to use as the header (i.e., the skiprows value).
    Returns 0 if no matching row is found (use first row as header).
    """
    kw_lower = [k.lower() for k in keywords]
    for i, row in enumerate(raw_rows):
        row_lower = [str(cell).lower() for cell in row]
        if all(any(kw in cell for cell in row_lower) for kw in kw_lower):
            return i
    return 0


# ---------------------------------------------------------------------------
# CSV loaders
# ---------------------------------------------------------------------------

def load_projection(filepath: str) -> pd.DataFrame:
    """
    Load a projection CSV, auto-detecting the header row by scanning for
    expected column keywords ('unit', 'desc').

    Falls back to skiprows=7 (historical default for PDF-extracted projection
    CSVs) if auto-detection fails.  Adjust this constant if the CSV format
    changes.
    """
    try:
        # Read a small slice to detect where the real header is
        raw = pd.read_csv(filepath, header=None, nrows=20)
        skip = _find_header_row(raw.values.tolist(), ["unit", "desc"])
        return pd.read_csv(filepath, skiprows=skip)
    except (ValueError, TypeError):
        # NOTE: skip=7 is the historical default for PDF-extracted projection CSVs
        skip = 7
        return pd.read_csv(filepath, skiprows=skip)


def load_rent_roll(filepath: str) -> pd.DataFrame:
    """
    Load a rent roll CSV, auto-detecting the header row by scanning for
    expected column keywords ('unit', 'status').

    Falls back to skiprows=6 (historical default for PDF-extracted rent roll
    CSVs) if auto-detection fails.  Adjust this constant if the CSV format
    changes.
    """
    try:
        # Read a small slice to detect where the real header is
        raw = pd.read_csv(filepath, header=None, nrows=20)
        skip = _find_header_row(raw.values.tolist(), ["unit", "status"])
        return pd.read_csv(filepath, skiprows=skip)
    except (ValueError, TypeError):
        # NOTE: skip=6 is the historical default for PDF-extracted rent roll CSVs
        skip = 6
        return pd.read_csv(filepath, skiprows=skip)


# ---------------------------------------------------------------------------
# Column detection helper
# ---------------------------------------------------------------------------

def _find_column_by_keywords(
    df: pd.DataFrame,
    keywords: list,
    fallback_index: int = 0,
) -> str:
    """
    Return the first column name whose lowercased string contains any of the
    given keywords.  Falls back to the column at *fallback_index* (clamped to
    a valid range) when no keyword match is found.
    """
    match = next(
        (c for c in df.columns if any(kw in str(c).lower() for kw in keywords)),
        None,
    )
    if match is not None:
        return match
    safe_index = min(fallback_index, len(df.columns) - 1)
    return df.columns[safe_index]


# ---------------------------------------------------------------------------
# Metrics computation
# ---------------------------------------------------------------------------

def compute_metrics(
    proj_df: pd.DataFrame,
    rent_roll_df: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """
    Compute audit metrics from projection and (optionally) rent roll DataFrames.

    Returns a DataFrame with columns:
      - Unit              : unit identifier
      - Monthly_Projection: projected charge for the current calendar month
      - Months_Remaining  : months until lease end (0 when no lease data)
      - Total_Lease_Loss  : Monthly_Projection * Months_Remaining * -1
                           (negative values represent revenue at risk)
    """
    today = datetime.today()
    current_month_col = today.strftime("%b %Y")  # e.g., "Mar 2026"

    # ------------------------------------------------------------------
    # Identify the description column dynamically by name pattern.
    # Uses 'desc', 'transaction', and 'category' as keywords; 'type' is
    # intentionally omitted because compound names like 'Unit Type' would
    # produce false positives.  Falls back to index 2 when available,
    # otherwise uses the last column.
    # ------------------------------------------------------------------
    desc_col = _find_column_by_keywords(
        proj_df,
        keywords=["desc", "transaction", "category"],
        fallback_index=2,
    )

    # Identify unit column
    unit_col = _find_column_by_keywords(
        proj_df,
        keywords=["unit", "id"],
        fallback_index=0,
    )

    proj_df = proj_df.copy()

    # Monthly projection for the current month (0.0 when column is absent)
    if current_month_col in proj_df.columns:
        proj_df["Monthly_Projection"] = proj_df[current_month_col].apply(resilient_read)
    else:
        proj_df["Monthly_Projection"] = 0.0

    # ------------------------------------------------------------------
    # Build unit → months_remaining mapping from rent roll
    # ------------------------------------------------------------------
    months_remaining_map: dict = {}
    if rent_roll_df is not None and not rent_roll_df.empty:
        rr = rent_roll_df.copy()
        rr.columns = [str(c).strip().lower().replace(" ", "_") for c in rr.columns]

        lease_end_col = next(
            (c for c in rr.columns if any(kw in c for kw in ["lease_end", "end_date", "expiry"])),
            None,
        )
        if lease_end_col:
            rr["_lease_end_dt"] = pd.to_datetime(rr[lease_end_col], errors="coerce")
            rr_unit_col = next(
                (c for c in rr.columns if "unit" in c),
                rr.columns[0],
            )
            for _, row in rr.drop_duplicates(subset=[rr_unit_col]).iterrows():
                uid = str(row[rr_unit_col]).strip()
                end_dt = row["_lease_end_dt"]
                if pd.notna(end_dt):
                    delta = (end_dt.year - today.year) * 12 + (end_dt.month - today.month)
                    months_remaining_map[uid] = max(delta, 0)

    # ------------------------------------------------------------------
    # Aggregate projections per unit and compute derived metrics
    # ------------------------------------------------------------------
    unit_proj = (
        proj_df.groupby(unit_col)["Monthly_Projection"]
        .sum()
        .reset_index()
        .rename(columns={unit_col: "Unit"})
    )

    unit_proj["Unit"] = unit_proj["Unit"].astype(str).str.strip()
    unit_proj["Months_Remaining"] = (
        unit_proj["Unit"].map(months_remaining_map).fillna(0).astype(int)
    )
    unit_proj["Total_Lease_Loss"] = (
        unit_proj["Monthly_Projection"] * unit_proj["Months_Remaining"] * -1
    )

    return unit_proj
