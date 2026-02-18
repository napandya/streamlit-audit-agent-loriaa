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
        if not table or len(table) < 1:
            return
        
        # Check if this table has the format: Unit, Unit Type, Category, Month1, Month2, ...
        # The ResMan format has columns like: Unit | Unit Type | Category | Feb 2026 | Mar 2026 | ...
        
        for row in table:
            if not row or len(row) < 4:
                continue
            
            # Check if first column contains unit info
            unit_info = self._extract_unit_info(row[0] if row[0] else "")
            
            if unit_info and len(row) >= 4:
                unit_number = unit_info['unit_number']
                resident_name = unit_info['resident_name']
                
                # Skip summary rows (like "Concession", "Employee Unit Rent Allowance", etc.)
                if not unit_number.isdigit():
                    continue
                
                # Create or update Unit object
                unit = Unit(
                    unit_id=f"unit_{unit_number}",
                    unit_number=unit_number,
                    resident_name=clean_resident_name(resident_name) if resident_name else None,
                    is_employee_unit=is_employee_unit(resident_name) if resident_name else False
                )
                canonical_model.add_unit(unit)
                
                # Column 1 is unit type (skip it)
                # Column 2 is category/description
                charge_description = row[2] if len(row) > 2 else ""
                
                if not charge_description:
                    continue
                
                # Normalize category
                category, subcategory = canonical_model.normalize_category(charge_description)
                
                # Columns 3+ are monthly amounts
                # We need to figure out which months these represent
                # For now, assume they start with current month and go forward
                from datetime import date
                start_month = date(2026, 2, 1)  # Feb 2026 from PDF header
                
                for idx in range(3, len(row)):
                    amount_str = row[idx]
                    amount = parse_currency(amount_str)
                    
                    if amount != 0:  # Only add non-zero transactions
                        # Calculate month offset
                        month_offset = idx - 3
                        month = start_month.month + month_offset
                        year = start_month.year
                        
                        # Handle year rollover
                        while month > 12:
                            month -= 12
                            year += 1
                        
                        month_date = date(year, month, 1)
                        
                        # Make concessions and credits negative
                        if category in ['concession', 'credit']:
                            amount = -abs(amount)
                        
                        transaction = RecurringTransaction(
                            transaction_id=generate_id("txn"),
                            unit_id=f"unit_{unit_number}",
                            unit_number=unit_number,
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
        Examples: 
        - "0201 - Luis Garcia"
        - "0202 - *Clayton Curtis" (employee unit)
        - "0203 - Marvin Hunt,\nJacquelyn Hunt" (multi-line)
        """
        if not cell_text:
            return None
        
        # Clean up multi-line text
        cell_text = cell_text.replace('\n', ' ').strip()
        
        # Pattern: unit number (3-4 digits), dash, resident name
        patterns = [
            r'^(\d{3,4})\s*[-–]\s*(.+)$',  # "0205 - Name" or "0202 - Name"
            r'(?:Unit\s+)?(\d+)\s*[-–]\s*(.+)',  # "Unit 0205 - Name"
            r'(?:Unit\s+)?([A-Za-z0-9]+)\s*[-–]\s*(.+)',  # Alphanumeric unit
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
