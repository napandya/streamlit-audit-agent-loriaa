"""
Word Document Parser for recurring transaction data
"""
from docx import Document
from typing import List, Optional
from datetime import date
import re

from models.unit import Unit, RecurringTransaction
from models.canonical_model import CanonicalModel
from utils.helpers import parse_currency, parse_month, clean_unit_number, generate_id, is_employee_unit, clean_resident_name


class WordParser:
    """
    Parses Word documents containing recurring transaction data
    Handles tables within Word documents
    """
    
    def __init__(self):
        pass
    
    def parse(self, doc_path: str, canonical_model: CanonicalModel) -> bool:
        """
        Parse a Word document and populate the canonical model
        Returns True if successful, False otherwise
        """
        try:
            doc = Document(doc_path)
            
            # Process all tables in the document
            for table in doc.tables:
                self._process_table(table, canonical_model)
            
            return True
        
        except Exception as e:
            print(f"Error parsing Word document: {e}")
            return False
    
    def _process_table(self, table, canonical_model: CanonicalModel):
        """Process a table from the Word document"""
        if len(table.rows) < 2:
            return
        
        # First row is typically headers
        header_row = table.rows[0]
        headers = [cell.text.strip() for cell in header_row.cells]
        
        # Try to identify month columns
        month_columns = {}
        for idx, header in enumerate(headers):
            month_date = parse_month(header)
            if month_date:
                month_columns[idx] = month_date
        
        current_unit = None
        current_resident = None
        
        # Process data rows
        for row in table.rows[1:]:
            cells = [cell.text.strip() for cell in row.cells]
            
            if not cells or len(cells) < 2:
                continue
            
            # Check if this is a unit header row
            unit_info = self._extract_unit_info(cells[0])
            if unit_info:
                current_unit = unit_info['unit_number']
                current_resident = unit_info.get('resident_name')
                
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
            if current_unit and cells[0]:
                charge_description = cells[0]
                category, subcategory = canonical_model.normalize_category(charge_description)
                
                # If we have month columns, process them
                if month_columns:
                    for col_idx, month_date in month_columns.items():
                        if col_idx < len(cells):
                            amount = parse_currency(cells[col_idx])
                            
                            if amount != 0:
                                transaction = RecurringTransaction(
                                    transaction_id=generate_id("txn"),
                                    unit_id=f"unit_{current_unit}",
                                    unit_number=current_unit,
                                    category=category,
                                    subcategory=subcategory,
                                    amount=amount,
                                    month=month_date,
                                    description=charge_description,
                                    source="word"
                                )
                                canonical_model.add_transaction(transaction)
                else:
                    # Simple format: just description and amount
                    if len(cells) > 1:
                        amount = parse_currency(cells[1])
                        if amount != 0:
                            transaction = RecurringTransaction(
                                transaction_id=generate_id("txn"),
                                unit_id=f"unit_{current_unit}",
                                unit_number=current_unit,
                                category=category,
                                subcategory=subcategory,
                                amount=amount,
                                month=None,
                                description=charge_description,
                                source="word"
                            )
                            canonical_model.add_transaction(transaction)
    
    def _extract_unit_info(self, cell_text: str) -> Optional[dict]:
        """
        Extract unit number and resident name from a cell
        """
        if not cell_text:
            return None
        
        patterns = [
            r'(?:Unit\s+)?(\d+)\s*[-–]\s*(.+)',
            r'(?:Unit\s+)?([A-Za-z0-9]+)\s*[-–]\s*(.+)',
            r'Unit\s+(\d+)',
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
