"""
ingestion.parsers — multi-format document parsers returning ParsedDocument.
"""
from dataclasses import dataclass, field
from typing import Optional
import pandas as pd


@dataclass
class ParsedDocument:
    """Normalised result returned by every parser."""
    file_name: str
    file_type: str
    raw_text: str
    dataframe: Optional[pd.DataFrame] = None
    document_type: Optional[str] = None  # rent_roll | projection | concession | unknown


def detect_document_type(file_name: str, content: str = "") -> str:
    """
    Heuristic document-type detection.

    Returns one of: "rent_roll", "projection", "concession", "unknown".
    """
    text = (file_name + " " + content).lower()
    if "rent roll" in text or "rent_roll" in text:
        return "rent_roll"
    if "projection" in text or "recurring transaction" in text:
        return "projection"
    if "concession" in text:
        return "concession"
    return "unknown"
