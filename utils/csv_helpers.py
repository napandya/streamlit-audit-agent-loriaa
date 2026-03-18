"""
Shared CSV loading and property-name utilities for the LiveNjoy audit system.

Centralises the encoding-fallback CSV reader and the filename → property-name
derivation logic so that ``engine/resman_rules.py`` and
``ingestion/resman_csv_loader.py`` share a single implementation.
"""
from __future__ import annotations

import pandas as pd

from config.fee_schedules import PROPERTY_MAP

# ---------------------------------------------------------------------------
# Keyword fallback map (supplements the code map in PROPERTY_MAP)
# ---------------------------------------------------------------------------
_KEYWORD_MAP: dict[str, str] = {
    "crossing": "Crossings at Irving",
    "irving": "Crossings at Irving",
    "taylor": "Parks on Taylor",
    "highland": "Highland Park",
    "prada": "La Prada",
    "village": "Village Green",
    "valencia": "Valencia Plaza",
    "western": "Western Station",
}


def derive_property(filename: str) -> str:
    """
    Map a ResMan export filename to the canonical full property name.

    Resolution order:
    1. First word of the filename matches a short code in ``PROPERTY_MAP``.
    2. Keyword scan of the lower-cased filename using ``_KEYWORD_MAP``.
    3. Fallback: return the first word of the filename unchanged.
    """
    first_word = filename.split(" ")[0].replace(",", "").upper()
    if first_word in PROPERTY_MAP:
        return PROPERTY_MAP[first_word]

    fname_lower = filename.lower()
    for keyword, prop in _KEYWORD_MAP.items():
        if keyword in fname_lower:
            return prop

    return filename.split(" ")[0]


def read_csv_robust(fpath: str, **kwargs) -> pd.DataFrame:
    """
    Read a CSV file, trying encodings ``utf-8-sig → cp1252 → latin-1``.

    ResMan exports from Windows often use the cp1252 or latin-1 encoding.
    The three-tier fallback ensures they load correctly regardless of the
    source machine locale.

    Raises
    ------
    ValueError
        If none of the three encodings succeed.
    """
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return pd.read_csv(fpath, encoding=enc, **kwargs)
        except UnicodeDecodeError:
            continue
    raise ValueError(
        f"Could not decode '{fpath}' with utf-8-sig, cp1252, or latin-1."
    )
