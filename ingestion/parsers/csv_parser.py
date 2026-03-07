"""
CSV parser — returns a ParsedDocument.
"""
import re
from pathlib import Path
from typing import Optional

import pandas as pd

from ingestion.parsers import ParsedDocument, detect_document_type


# Month abbreviation pattern used to detect true header rows in ResMan exports.
_MONTH_PATTERN = re.compile(
    r"^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+20\d{2}$",
    re.IGNORECASE,
)

# Keywords that appear in a genuine data-header row (not a metadata/title row).
_HEADER_KEYWORDS = {
    "unit", "unit type", "category", "residents", "status",
    "market rent", "sq. feet", "sq ft", "type", "charges", "description",
}


def _detect_best_header_row(raw: pd.DataFrame) -> Optional[int]:
    """
    Scan the first 30 rows of a raw (no-header) DataFrame to find the true
    header row in a ResMan multi-row CSV.

    A candidate header row must contain at least two month-like column values
    (e.g. "Feb 2026") AND at least one recognised keyword (e.g. "Unit",
    "Category").  When multiple rows qualify the *last* one wins, because
    ResMan CSVs place the most-granular (per-unit) section at the bottom.

    Returns the 0-indexed row number, or None if no ResMan-style header is
    detected (plain CSV — use pandas default header=0 behaviour).
    """
    best_row: Optional[int] = None
    best_month_count = 0

    for idx in range(min(len(raw), 30)):
        row = raw.iloc[idx]
        values = row.dropna().astype(str).str.strip()
        month_count = sum(1 for v in values if _MONTH_PATTERN.match(v))
        has_keyword = any(v.lower() in _HEADER_KEYWORDS for v in values)

        if month_count >= 2 and has_keyword:
            if month_count >= best_month_count:
                best_month_count = month_count
                best_row = idx

    return best_row


def _read_csv_resilient(file_path: str) -> pd.DataFrame:
    """Try utf-8 then latin-1 encoding, with ResMan multi-row header detection."""
    raw: Optional[pd.DataFrame] = None
    encoding_used = "utf-8"

    for enc in ("utf-8", "latin-1"):
        try:
            raw = pd.read_csv(file_path, header=None, encoding=enc)
            encoding_used = enc
            break
        except UnicodeDecodeError:
            continue

    if raw is None or raw.empty:
        return pd.DataFrame()

    header_row = _detect_best_header_row(raw)
    if header_row is not None and header_row > 0:
        try:
            return pd.read_csv(file_path, header=header_row, encoding=encoding_used)
        except Exception:
            pass

    # Default: header at row 0 (plain CSV or header already at top)
    try:
        return pd.read_csv(file_path, encoding=encoding_used)
    except Exception:
        return pd.DataFrame()


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

    Args:
        file_path: Path to the CSV file.

    Returns:
        ParsedDocument with dataframe, raw_text, and detected document_type.
    """
    path = Path(file_path)
    try:
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
