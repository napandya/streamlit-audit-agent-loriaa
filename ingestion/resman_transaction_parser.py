"""
Parser for ResMan Transaction List (Credits) CSV exports.

Each file has a 6-row metadata header followed by the real column header
on row 7 (index 6).  Category sub-header rows and Total rows are dropped
so only actual transaction rows are returned.
"""
from __future__ import annotations

import pandas as pd


def parse_resman_transaction_csv(file_path: str) -> tuple[str, pd.DataFrame]:
    """
    Parse a ResMan Transaction List (Credits) CSV.

    Returns
    -------
    (property_name, clean_dataframe)

    * property_name  – read from row 0, column 0
    * clean_dataframe – real transaction rows with numeric Amount / charge columns
    """
    # --- Read property name from row 0, column 0 ---
    for enc in ("utf-8", "latin-1"):
        try:
            with open(file_path, encoding=enc) as fh:
                first_line = fh.readline()
            break
        except UnicodeDecodeError:
            continue
    else:
        with open(file_path, encoding="latin-1") as fh:
            first_line = fh.readline()
    property_name = first_line.split(",")[0].strip().strip('"')

    # --- Read CSV skipping the 6 metadata rows; row 6 becomes the header ---
    # Try UTF-8 first, fall back to latin-1 for Windows-1252-encoded files
    for encoding in ("utf-8", "latin-1"):
        try:
            df = pd.read_csv(file_path, skiprows=6, dtype=str, on_bad_lines="skip", encoding=encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        df = pd.read_csv(file_path, skiprows=6, dtype=str, on_bad_lines="skip", encoding="latin-1")

    # Normalise column names (strip surrounding whitespace)
    df.columns = [str(c).strip() for c in df.columns]

    # --- Drop repeated header rows (occasionally appear between sections) ---
    if "Date" in df.columns:
        df = df[df["Date"].str.strip() != "Date"]

    # --- Drop category sub-header rows ---
    # These have the category name in the Date column and all other cols empty.
    # Pattern: Date cell contains "Credit -" or "Debit -"
    if "Date" in df.columns:
        df = df[~df["Date"].str.contains(r"^Credit\s*-|^Debit\s*-", na=False, regex=True)]

    # --- Drop total rows ---
    if "Date" in df.columns:
        df = df[~df["Date"].str.startswith("Total:", na=False)]

    # --- Keep only rows that have a non-empty Unit value ---
    if "Unit" in df.columns:
        df = df[df["Unit"].notna() & (df["Unit"].str.strip() != "")]

    # --- Convert numeric columns (amounts may have comma thousands-separators) ---
    numeric_cols = [
        "Amount",
        "Gross Payments",
        "In Period Reversal",
        "Out Of Period Reversal",
        "Period Charges",
        "Prior Charges",
        "Post Charges",
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = (
                df[col]
                .str.replace(",", "", regex=False)
                .pipe(pd.to_numeric, errors="coerce")
                .fillna(0.0)
            )

    # --- Fill string columns so NaN becomes empty string ---
    str_fill_cols = ["Reverse Date", "Reference", "Notes", "Description", "Name", "Related"]
    for col in str_fill_cols:
        if col in df.columns:
            df[col] = df[col].fillna("")

    df = df.reset_index(drop=True)
    return property_name, df
