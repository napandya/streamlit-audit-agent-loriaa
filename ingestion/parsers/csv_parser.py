"""
CSV parser — returns a ParsedDocument.

Handles plain CSVs *and* ResMan property-management exports whose true header
row is buried inside metadata rows (property name, company, report title, …).
"""
import re
from pathlib import Path
from typing import Optional

import pandas as pd

from ingestion.parsers import ParsedDocument, detect_document_type

# Keywords that indicate a genuine data header row
_HEADER_KEYWORDS = {
    "unit", "unit type", "category", "status", "residents", "resident",
    "market rent", "sq. feet", "sq ft", "description", "charges",
    "type", "deposits", "balance", "move in",
}

# Regex for month-like column values (e.g. "Feb 2026", "January 2025")
_MONTH_RE = re.compile(
    r"^(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4}$",
    re.IGNORECASE,
)


def _read_csv_raw(file_path: str) -> pd.DataFrame:
    """Read a CSV with ``header=None`` (all rows as data) for inspection."""
    try:
        return pd.read_csv(file_path, header=None, encoding="utf-8", dtype=str)
    except UnicodeDecodeError:
        return pd.read_csv(file_path, header=None, encoding="latin-1", dtype=str)


def _read_csv_resilient(file_path: str, header: int = 0) -> pd.DataFrame:
    """Read a CSV with a specific header row.  Try utf-8 then latin-1."""
    try:
        return pd.read_csv(file_path, header=header, encoding="utf-8")
    except UnicodeDecodeError:
        return pd.read_csv(file_path, header=header, encoding="latin-1")


def _detect_best_header_row(file_path: str, max_scan: int = 30) -> Optional[int]:
    """
    Scan the first *max_scan* rows of a CSV (read with ``header=None``) and
    return the 0-based row index of the best header row.

    The heuristic picks the **last** row that contains both:
      • at least one cell matching a known header keyword, AND
      • at least two cells that look like month values (e.g. "Feb 2026").

    Choosing the *last* match selects the most-granular per-unit section in
    ResMan's multi-section layout.

    Returns ``None`` when no multi-row header is detected (plain CSV).
    """
    try:
        raw = _read_csv_raw(file_path)
    except Exception:
        return None

    best: Optional[int] = None
    scan_limit = min(max_scan, len(raw))

    for idx in range(scan_limit):
        row_values = [str(v).strip().lower() for v in raw.iloc[idx] if pd.notna(v)]
        month_count = sum(1 for v in row_values if _MONTH_RE.match(v))
        keyword_hit = any(v in _HEADER_KEYWORDS for v in row_values)

        if keyword_hit and month_count >= 2:
            best = idx  # keep scanning — last match wins

    return best


def _skip_metadata_rows(df: pd.DataFrame) -> pd.DataFrame:
    """
    Drop rows where most columns are empty (i.e., only one or zero non-empty
    cells), which typically represent blank separator or title rows in
    property-management exports.
    """
    if df.empty:
        return df

    def _is_metadata_row(row) -> bool:
        non_empty = row.dropna().astype(str).str.strip().str.len() > 0
        return non_empty.sum() <= 1  # Almost empty row

    mask = df.apply(_is_metadata_row, axis=1)
    cleaned = df[~mask].reset_index(drop=True)
    return cleaned if not cleaned.empty else df


def parse_csv(file_path: str) -> ParsedDocument:
    """
    Parse a CSV file and return a ParsedDocument.

    For ResMan exports with multi-row headers the parser auto-detects the real
    header row so that column names like ``"Unit"``, ``"Category"``,
    ``"Feb 2026"`` etc. are used instead of metadata values.

    Args:
        file_path: Path to the CSV file.

    Returns:
        ParsedDocument with dataframe, raw_text, and detected document_type.
    """
    path = Path(file_path)
    try:
        best_header = _detect_best_header_row(str(path))
        if best_header is not None:
            df = _read_csv_resilient(str(path), header=best_header)
        else:
            df = _read_csv_resilient(str(path))
        df = _skip_metadata_rows(df)
        raw_text = df.to_string(index=False)
    except Exception:
        df = pd.DataFrame()
        raw_text = ""

    doc_type = detect_document_type(path.name, raw_text[:2000])

    return ParsedDocument(
        file_name=path.name,
        file_type="csv",
        raw_text=raw_text,
        dataframe=df,
        document_type=doc_type,
    )
