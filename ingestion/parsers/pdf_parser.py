"""
PDF parser — returns a ParsedDocument.
"""
from pathlib import Path
from typing import Optional

import pdfplumber
import pandas as pd

from ingestion.parsers import ParsedDocument, detect_document_type


def parse_pdf(file_path: str) -> ParsedDocument:
    """
    Parse a PDF file using pdfplumber and return a ParsedDocument.
    Extracts all text and any tables as a DataFrame.
    """
    path = Path(file_path)
    all_text_parts: list[str] = []
    all_tables: list[pd.DataFrame] = []

    with pdfplumber.open(str(path)) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                all_text_parts.append(text)

            tables = page.extract_tables()
            for tbl in tables:
                if tbl and len(tbl) > 1:
                    header = tbl[0]
                    rows = tbl[1:]
                    try:
                        df = pd.DataFrame(rows, columns=header)
                        all_tables.append(df)
                    except Exception:
                        pass

    raw_text = "\n".join(all_text_parts)
    combined_df: Optional[pd.DataFrame] = None
    if all_tables:
        try:
            combined_df = pd.concat(all_tables, ignore_index=True)
        except Exception:
            combined_df = all_tables[0]

    doc_type = detect_document_type(path.name, raw_text[:2000])

    return ParsedDocument(
        file_name=path.name,
        file_type="pdf",
        raw_text=raw_text,
        dataframe=combined_df,
        document_type=doc_type,
    )
