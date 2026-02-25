"""
Excel parser (.xlsx / .xls) — returns a ParsedDocument.
"""
from pathlib import Path

import pandas as pd

from ingestion.parsers import ParsedDocument, detect_document_type


def _skip_metadata_rows(df: pd.DataFrame) -> pd.DataFrame:
    """Drop rows where most columns are empty."""
    if df.empty:
        return df

    def _is_metadata_row(row) -> bool:
        non_empty = row.dropna().astype(str).str.strip().str.len() > 0
        return non_empty.sum() <= 1

    mask = df.apply(_is_metadata_row, axis=1)
    cleaned = df[~mask].reset_index(drop=True)
    return cleaned if not cleaned.empty else df


def parse_excel(file_path: str) -> ParsedDocument:
    """
    Parse an Excel file (.xlsx or .xls) and return a ParsedDocument.
    """
    path = Path(file_path)
    ext = path.suffix.lower()

    engine = "openpyxl" if ext == ".xlsx" else "xlrd"
    try:
        df = pd.read_excel(str(path), engine=engine)
    except Exception:
        # Fallback — let pandas pick the engine
        df = pd.read_excel(str(path))

    df = _skip_metadata_rows(df)
    raw_text = df.to_string(index=False)
    doc_type = detect_document_type(path.name, raw_text[:2000])

    return ParsedDocument(
        file_name=path.name,
        file_type=ext.lstrip("."),
        raw_text=raw_text,
        dataframe=df,
        document_type=doc_type,
    )
