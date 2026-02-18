"""
PDF Parser for ResMan Recurring Transaction Projection reports
"""
import pdfplumber
from typing import List, Dict, Optional
from datetime import date
import re
from pathlib import Path

from models.unit import Unit, RecurringTransaction
from models.canonical_model import CanonicalModel
from utils.helpers import parse_currency, parse_month, clean_unit_number, generate_id, is_employee_unit, clean_resident_name


class PDFParser:
    """
    Parses ResMan recurring transaction projection PDF reports
    Handles multi-page, unit-by-unit breakdown with monthly columns
    """
    
    def __init__(self):
        self.units: List[Unit] = []
        self.transactions: List[RecurringTransaction] = []
    
    def parse(self, pdf_path: str, canonical_model: CanonicalModel) -> bool:
        """
        Parse a PDF file and populate the canonical model
        Returns True if successful, False otherwise
        """
        try:
            with pdfplumber.open(pdf_path) as pdf:
                # Extract all text and tables from all pages
                for page_num, page in enumerate(pdf.pages):
                    # Extract tables from the page
                    tables = page.extract_tables()
                    
                    for table in tables:
                        if table:
                            self._process_table(table, canonical_model)
            
            return True
        
        except Exception as e:
            print(f"Error parsing PDF: {e}")
            return False
    
    def _process_table(self, table: List[List[str]], canonical_model: CanonicalModel):
        """Process a table extracted from the PDF"""
        if not table or len(table) < 2:
            return
        
        # First row typically contains headers (months)
        header_row = table[0]
        month_columns = self._extract_month_columns(header_row)
        
        # Process each subsequent row
        current_unit = None
        current_resident = None
        
        for row in table[1:]:
            if not row or len(row) < 2:
                continue
            
            # Check if this is a unit header row
            unit_match = self._extract_unit_info(row[0] if row[0] else "")
            if unit_match:
                current_unit = unit_match['unit_number']
                current_resident = unit_match['resident_name']
                
                # Create Unit object
                unit = Unit(
                    unit_id=f"unit_{current_unit}",
                    unit_number=current_unit,
                    resident_name=clean_resident_name(current_resident) if current_resident else None,
                    is_employee_unit=is_employee_unit(current_resident) if current_resident else False
                )
                canonical_model.add_unit(unit)
                continue
            
            # Process charge row if we have a current unit
            if current_unit and len(row) > 0:
                charge_description = row[0] if row[0] else ""
                
                # Normalize category
                category, subcategory = canonical_model.normalize_category(charge_description)
                
                # Process amounts for each month
                for month_idx, month_date in month_columns.items():
                    if month_idx < len(row):
                        amount_str = row[month_idx]
                        amount = parse_currency(amount_str)
                        
                        if amount != 0:  # Only add non-zero transactions
                            transaction = RecurringTransaction(
                                transaction_id=generate_id("txn"),
                                unit_id=f"unit_{current_unit}",
                                unit_number=current_unit,
                                category=category,
                                subcategory=subcategory,
                                amount=amount,
                                month=month_date,
                                description=charge_description,
                                source="pdf"
                            )
                            canonical_model.add_transaction(transaction)
    
    def _extract_month_columns(self, header_row: List[str]) -> Dict[int, date]:
        """
        Extract month columns from header row
        Returns dict of {column_index: date}
        """
        month_columns = {}
        
        for idx, cell in enumerate(header_row):
            if cell:
                month_date = parse_month(cell)
                if month_date:
                    month_columns[idx] = month_date
        
        return month_columns
    
    def _extract_unit_info(self, cell_text: str) -> Optional[Dict[str, str]]:
        """
        Extract unit number and resident name from a cell
        Example: "Unit 0205 - Victoria Braden" or "0205 - *Clayton Curtis"
        """
        if not cell_text:
            return None
        
        # Pattern: optional "Unit" prefix, unit number, dash, resident name
        patterns = [
            r'(?:Unit\s+)?(\d+)\s*[-–]\s*(.+)',  # "Unit 0205 - Name" or "0205 - Name"
            r'(?:Unit\s+)?([A-Za-z0-9]+)\s*[-–]\s*(.+)',  # Alphanumeric unit
            r'Unit\s+(\d+)',  # Just "Unit 0205"
        ]
        
        for pattern in patterns:
            match = re.search(pattern, cell_text, re.IGNORECASE)
            if match:
                if len(match.groups()) >= 2:
                    return {
                        'unit_number': clean_unit_number(match.group(1)),
                        'resident_name': match.group(2).strip()
                    }
                elif len(match.groups()) == 1:
                    return {
                        'unit_number': clean_unit_number(match.group(1)),
                        'resident_name': None
                    }
        
        return None
