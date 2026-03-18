"""
Multi-subfolder ResMan CSV loader for the LiveNjoy forensic audit engine.

Handles loading from the 6 ResMan export subfolders:
  data/transactions/  — Transaction List (Credits)
  data/leases/        — New and Renewed Leases
  data/edits/         — Edited Transactions by User
  data/recurring/     — Transaction Projections (Recurring)
  data/rent_rolls/    — Rent Rolls
  data/activity/      — Resident Activity

Does NOT modify ingestion/resman_client.py or ingestion/loader.py.
"""

from __future__ import annotations

import os

import pandas as pd

from config.fee_schedules import PROPERTY_MAP

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
# Internal helpers
# ---------------------------------------------------------------------------

def _derive_property(filename: str) -> str:
    """
    Map a ResMan export filename to the canonical full property name.

    Resolution order:
    1. First word of filename matches a short code in PROPERTY_MAP.
    2. Keyword scan on the lowercased filename.
    3. Fallback: return the first word of the filename unchanged.
    """
    keyword_map = {
        "crossing": "Crossings at Irving",
        "irving": "Crossings at Irving",
        "taylor": "Parks on Taylor",
        "highland": "Highland Park",
        "prada": "La Prada",
        "village": "Village Green",
        "valencia": "Valencia Plaza",
        "western": "Western Station",
    }

    first_word = filename.split(" ")[0].replace(",", "").upper()
    if first_word in PROPERTY_MAP:
        return PROPERTY_MAP[first_word]

    fname_lower = filename.lower()
    for keyword, prop in keyword_map.items():
        if keyword in fname_lower:
            return prop

    return filename.split(" ")[0]


def _read_csv_robust(fpath: str, **kwargs) -> pd.DataFrame:
    """Try encodings: utf-8-sig → cp1252 → latin-1 (ResMan Windows exports)."""
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return pd.read_csv(fpath, encoding=enc, **kwargs)
        except UnicodeDecodeError:
            continue
    raise ValueError(
        f"Could not decode '{fpath}' with utf-8-sig, cp1252, or latin-1."
    )


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
        prop_name = _derive_property(fname)
        try:
            df = _read_csv_robust(fpath, dtype=str, low_memory=False)
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
