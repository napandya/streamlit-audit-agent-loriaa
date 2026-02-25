"""
CSV parser — returns a ParsedDocument.
"""
from pathlib import Path
from typing import Optional

import pandas as pd

from ingestion.parsers import ParsedDocument, detect_document_type


def _read_csv_resilient(file_path: str) -> pd.DataFrame:
    """Try utf-8 then latin-1 encoding."""
    try:
        return pd.read_csv(file_path, encoding="utf-8")
    except UnicodeDecodeError:
        return pd.read_csv(file_path, encoding="latin-1")


def _skip_metadata_rows(df: pd.DataFrame) -> pd.DataFrame:
    """
    Drop rows where most columns are empty or the first non-empty cell looks
    like property name / date metadata (not tabular data).
    """
    if df.empty:
        return df

    threshold = max(1, len(df.columns) // 2)

    def _is_metadata_row(row) -> bool:
        non_empty = row.dropna().astype(str).str.strip().str.len() > 0
        if non_empty.sum() <= 1:
            return True  # Almost empty row
        return False

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
