"""
Unified file loader - routes files to appropriate parsers.
Now returns (bool, str, Optional[ParsedDocument]) as well as populating
the CanonicalModel for backward-compatibility.
"""
from pathlib import Path
from typing import Optional, Tuple

from models.canonical_model import CanonicalModel
from ingestion.parsers import ParsedDocument
from ingestion.parsers.csv_parser import parse_csv
from ingestion.parsers.excel_parser import parse_excel
from ingestion.parsers.pdf_parser import parse_pdf
from ingestion.parsers.docx_parser import parse_docx

# Legacy parsers kept for CanonicalModel population
from ingestion.pdf_parser import PDFParser
from ingestion.excel_parser import ExcelParser
from ingestion.word_parser import WordParser
from utils.validations import validate_file_extension


class FileLoader:
    """
    Unified file loader that routes files to the appropriate parser
    based on file extension.
    """

    SUPPORTED_EXTENSIONS = {
        "pdf": (PDFParser, parse_pdf),
        "xlsx": (ExcelParser, parse_excel),
        "xls": (ExcelParser, parse_excel),
        "csv": (ExcelParser, parse_csv),
        "docx": (WordParser, parse_docx),
    }

    def __init__(self):
        pass

    def load_file(
        self,
        file_path: str,
        canonical_model: Optional[CanonicalModel] = None,
    ) -> Tuple[bool, str, Optional[ParsedDocument]]:
        """
        Load a file, optionally populate the canonical model, and return
        a ParsedDocument.

        Args:
            file_path: Path to the file to load.
            canonical_model: Optional CanonicalModel instance to populate.

        Returns:
            (success: bool, message: str, parsed_doc: Optional[ParsedDocument])
        """
        path = Path(file_path)
        if not path.exists():
            return False, f"File not found: {file_path}", None

        extension = path.suffix.lower().lstrip(".")
        if extension not in self.SUPPORTED_EXTENSIONS:
            supported = ", ".join(self.SUPPORTED_EXTENSIONS.keys())
            return (
                False,
                f"Unsupported file type: {extension}. Supported types: {supported}",
                None,
            )

        legacy_parser_class, new_parser_fn = self.SUPPORTED_EXTENSIONS[extension]

        try:
            # --- New parser: returns ParsedDocument ---
            parsed_doc: Optional[ParsedDocument] = new_parser_fn(str(path))

            # --- Legacy parser: populates CanonicalModel (backward compat) ---
            if canonical_model is not None:
                legacy_parser = legacy_parser_class()
                legacy_parser.parse(str(path), canonical_model)

            return True, f"Successfully loaded {path.name}", parsed_doc

        except Exception as e:
            return False, f"Error loading {path.name}: {str(e)}", None

    @classmethod
    def get_supported_extensions(cls) -> list:
        """Get list of supported file extensions."""
        return list(cls.SUPPORTED_EXTENSIONS.keys())

    @classmethod
    def is_supported(cls, filename: str) -> bool:
        """Check if a filename has a supported extension."""
        extension = Path(filename).suffix.lower().lstrip(".")
        return extension in cls.SUPPORTED_EXTENSIONS
