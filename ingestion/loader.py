"""
Unified file loader - routes files to appropriate parsers
"""
from pathlib import Path
from typing import Optional

from models.canonical_model import CanonicalModel
from ingestion.pdf_parser import PDFParser
from ingestion.excel_parser import ExcelParser
from ingestion.word_parser import WordParser
from utils.validations import validate_file_extension


class FileLoader:
    """
    Unified file loader that routes files to the appropriate parser
    based on file extension
    """
    
    SUPPORTED_EXTENSIONS = {
        'pdf': PDFParser,
        'xlsx': ExcelParser,
        'xls': ExcelParser,
        'csv': ExcelParser,
        'docx': WordParser,
    }
    
    def __init__(self):
        pass
    
    def load_file(self, file_path: str, canonical_model: CanonicalModel) -> tuple[bool, str]:
        """
        Load a file and populate the canonical model
        
        Args:
            file_path: Path to the file to load
            canonical_model: CanonicalModel instance to populate
        
        Returns:
            (success: bool, message: str)
        """
        # Check if file exists
        path = Path(file_path)
        if not path.exists():
            return False, f"File not found: {file_path}"
        
        # Get file extension
        extension = path.suffix.lower().lstrip('.')
        
        # Validate extension
        if extension not in self.SUPPORTED_EXTENSIONS:
            supported = ', '.join(self.SUPPORTED_EXTENSIONS.keys())
            return False, f"Unsupported file type: {extension}. Supported types: {supported}"
        
        # Get appropriate parser
        parser_class = self.SUPPORTED_EXTENSIONS[extension]
        parser = parser_class()
        
        # Parse the file
        try:
            success = parser.parse(file_path, canonical_model)
            if success:
                return True, f"Successfully loaded {path.name}"
            else:
                return False, f"Failed to parse {path.name}"
        
        except Exception as e:
            return False, f"Error loading {path.name}: {str(e)}"
    
    @classmethod
    def get_supported_extensions(cls) -> list:
        """Get list of supported file extensions"""
        return list(cls.SUPPORTED_EXTENSIONS.keys())
    
    @classmethod
    def is_supported(cls, filename: str) -> bool:
        """Check if a filename has a supported extension"""
        extension = Path(filename).suffix.lower().lstrip('.')
        return extension in cls.SUPPORTED_EXTENSIONS
