"""
Multi-subfolder ResMan CSV loader for the LiveNjoy forensic audit engine.

Handles loading from the 6 ResMan export subfolders:
  data/transactions/  — Transaction List (Credits)
  data/leases/        — New and Renewed Leases
  data/edits/         — Edited Transactions by User
  data/recurring/     — Transaction Projections (Recurring)
  data/rent_rolls/    — Rent Rolls
  data/activity/      — Resident Activity

NOTE: ``engine/resman_rules.py`` contains its own specialised loaders that
parse each report type with the correct ``skiprows`` and column renaming.
Those specialised loaders are used by the production orchestrator
(``run_resman_audit``).  This module provides a **generic utility** for any
future code that needs raw DataFrames from these subfolders without the
report-type-specific parsing.

Does NOT modify ingestion/resman_client.py or ingestion/loader.py.
"""

from __future__ import annotations

import os

import pandas as pd

from utils.csv_helpers import derive_property, read_csv_robust

# ---------------------------------------------------------------------------
# REPORT TYPE SUBFOLDER NAMES
# ---------------------------------------------------------------------------
REPORT_SUBFOLDERS = [
    "transactions",
    "leases",
    "edits",
    "recurring",
    "rent_rolls",
    "activity",
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_subfolder(
    subfolder_path: str,
    report_type: str,
) -> list[tuple[str, pd.DataFrame]]:
    """
    Load all CSVs in a subfolder and return a list of (property_name, df) tuples.

    Parameters
    ----------
    subfolder_path:
        Absolute or relative path to the subfolder (e.g. ``"data/transactions"``).
    report_type:
        One of ``'transactions'``, ``'leases'``, ``'edits'``, ``'recurring'``,
        ``'rent_rolls'``, ``'activity'``. Used for logging only.

    Notes
    -----
    - Tries encodings: utf-8-sig, cp1252, latin-1.
    - Skips the ResMan 4-row header block (property name, company, report type,
      date/period) via ``skiprows=4`` and returns the raw DataFrame with the
      ResMan column headers intact so each engine's specialised loader can
      apply its own parsing logic.
    - Returns an empty list (not an error) if the subfolder is missing or empty.
    """
    if not os.path.exists(subfolder_path):
        return []

    csv_files = [
        f for f in os.listdir(subfolder_path) if f.lower().endswith(".csv")
    ]
    if not csv_files:
        return []

    results: list[tuple[str, pd.DataFrame]] = []

    for fname in sorted(csv_files):
        fpath = os.path.join(subfolder_path, fname)
        prop_name = derive_property(fname)
        try:
            df = read_csv_robust(fpath, dtype=str, low_memory=False)
            df["_property_name"] = prop_name
            df["_source_file"] = fname
            df["_report_type"] = report_type
            results.append((prop_name, df))
        except Exception as exc:  # noqa: BLE001
            print(f"  [resman_csv_loader] WARN {report_type}/{fname}: {exc}")

    return results


def load_all_resman_data(data_dir: str) -> dict[str, list[tuple[str, pd.DataFrame]]]:
    """
    Load all 6 ResMan export subfolders under *data_dir*.

    Returns a dict keyed by report_type; each value is a list of
    ``(property_name, df)`` tuples.  Missing or empty subfolders
    produce empty lists — never errors.

    Parameters
    ----------
    data_dir:
        Root data directory (e.g. ``"data"`` or ``"/abs/path/to/data"``).
    """
    output: dict[str, list[tuple[str, pd.DataFrame]]] = {}

    for report_type in REPORT_SUBFOLDERS:
        subfolder = os.path.join(data_dir, report_type)
        output[report_type] = load_subfolder(subfolder, report_type)

    return output
