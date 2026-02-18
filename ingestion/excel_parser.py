"""
Excel/CSV Parser for recurring transaction data
"""
import pandas as pd
from typing import List, Optional
from datetime import date
from pathlib import Path

from models.unit import Unit, RecurringTransaction
from models.canonical_model import CanonicalModel
from utils.helpers import parse_currency, parse_month, parse_date, clean_unit_number, generate_id, is_employee_unit, clean_resident_name


class ExcelParser:
    """
    Parses Excel and CSV files containing recurring transaction data
    Supports various formats with flexible column mapping
    """
    
    # Common column name variations
    UNIT_COLUMNS = ['unit', 'unit_number', 'unit #', 'unit_id', 'apt', 'apartment']
    RESIDENT_COLUMNS = ['resident', 'resident_name', 'name', 'tenant', 'tenant_name']
    AMOUNT_COLUMNS = ['amount', 'charge', 'total', 'value']
    MONTH_COLUMNS = ['month', 'date', 'period', 'month_date']
    DESCRIPTION_COLUMNS = ['description', 'charge_type', 'category', 'type', 'item']
    
    def __init__(self):
        pass
    
    def parse(self, file_path: str, canonical_model: CanonicalModel) -> bool:
        """
        Parse an Excel or CSV file and populate the canonical model
        Returns True if successful, False otherwise
        """
        try:
            # Determine file type and read accordingly
            file_ext = Path(file_path).suffix.lower()
            
            if file_ext == '.csv':
                df = pd.read_csv(file_path)
            elif file_ext in ['.xlsx', '.xls']:
                df = pd.read_excel(file_path)
            else:
                print(f"Unsupported file type: {file_ext}")
                return False
            
            # Try to identify the format
            if self._is_pivot_format(df):
                self._parse_pivot_format(df, canonical_model)
            else:
                self._parse_flat_format(df, canonical_model)
            
            return True
        
        except Exception as e:
            print(f"Error parsing Excel/CSV: {e}")
            return False
    
    def _is_pivot_format(self, df: pd.DataFrame) -> bool:
        """Check if the dataframe is in pivot format (months as columns)"""
        # Look for month-like column headers
        month_cols = 0
        for col in df.columns:
            if parse_month(str(col)):
                month_cols += 1
        
        return month_cols > 2  # Multiple month columns indicate pivot format
    
    def _parse_pivot_format(self, df: pd.DataFrame, canonical_model: CanonicalModel):
        """Parse pivot format (similar to PDF - months as columns)"""
        # Identify month columns
        month_columns = {}
        for col in df.columns:
            month_date = parse_month(str(col))
            if month_date:
                month_columns[col] = month_date
        
        # Find unit and description columns
        unit_col = self._find_column(df, self.UNIT_COLUMNS)
        desc_col = self._find_column(df, self.DESCRIPTION_COLUMNS)
        resident_col = self._find_column(df, self.RESIDENT_COLUMNS)
        
        current_unit = None
        current_resident = None
        
        for idx, row in df.iterrows():
            # Check for unit row
            if unit_col and pd.notna(row.get(unit_col)):
                unit_number = clean_unit_number(str(row[unit_col]))
                if unit_number:
                    current_unit = unit_number
                    current_resident = str(row[resident_col]) if resident_col and pd.notna(row.get(resident_col)) else None
                    
                    # Create Unit
                    unit = Unit(
                        unit_id=f"unit_{current_unit}",
                        unit_number=current_unit,
                        resident_name=clean_resident_name(current_resident) if current_resident else None,
                        is_employee_unit=is_employee_unit(current_resident) if current_resident else False
                    )
                    canonical_model.add_unit(unit)
            
            # Process charge row
            if current_unit and desc_col and pd.notna(row.get(desc_col)):
                description = str(row[desc_col])
                category, subcategory = canonical_model.normalize_category(description)
                
                # Process each month column
                for col_name, month_date in month_columns.items():
                    if col_name in row and pd.notna(row[col_name]):
                        amount = parse_currency(str(row[col_name]))
                        
                        if amount != 0:
                            transaction = RecurringTransaction(
                                transaction_id=generate_id("txn"),
                                unit_id=f"unit_{current_unit}",
                                unit_number=current_unit,
                                category=category,
                                subcategory=subcategory,
                                amount=amount,
                                month=month_date,
                                description=description,
                                source="excel"
                            )
                            canonical_model.add_transaction(transaction)
    
    def _parse_flat_format(self, df: pd.DataFrame, canonical_model: CanonicalModel):
        """Parse flat format (each row is a transaction)"""
        # Find required columns
        unit_col = self._find_column(df, self.UNIT_COLUMNS)
        amount_col = self._find_column(df, self.AMOUNT_COLUMNS)
        month_col = self._find_column(df, self.MONTH_COLUMNS)
        desc_col = self._find_column(df, self.DESCRIPTION_COLUMNS)
        resident_col = self._find_column(df, self.RESIDENT_COLUMNS)
        
        if not unit_col or not amount_col:
            print("Could not find required columns (unit, amount)")
            return
        
        # Track unique units
        units_seen = set()
        
        for idx, row in df.iterrows():
            if pd.isna(row.get(unit_col)) or pd.isna(row.get(amount_col)):
                continue
            
            unit_number = clean_unit_number(str(row[unit_col]))
            resident_name = str(row[resident_col]) if resident_col and pd.notna(row.get(resident_col)) else None
            
            # Create unit if not seen
            if unit_number and unit_number not in units_seen:
                units_seen.add(unit_number)
                unit = Unit(
                    unit_id=f"unit_{unit_number}",
                    unit_number=unit_number,
                    resident_name=clean_resident_name(resident_name) if resident_name else None,
                    is_employee_unit=is_employee_unit(resident_name) if resident_name else False
                )
                canonical_model.add_unit(unit)
            
            # Parse transaction
            amount = parse_currency(str(row[amount_col]))
            month_date = parse_month(str(row[month_col])) if month_col and pd.notna(row.get(month_col)) else None
            description = str(row[desc_col]) if desc_col and pd.notna(row.get(desc_col)) else "Charge"
            
            category, subcategory = canonical_model.normalize_category(description)
            
            transaction = RecurringTransaction(
                transaction_id=generate_id("txn"),
                unit_id=f"unit_{unit_number}",
                unit_number=unit_number,
                category=category,
                subcategory=subcategory,
                amount=amount,
                month=month_date,
                description=description,
                source="excel"
            )
            canonical_model.add_transaction(transaction)
    
    def _find_column(self, df: pd.DataFrame, possible_names: List[str]) -> Optional[str]:
        """Find a column by checking possible name variations"""
        df_columns_lower = {col.lower(): col for col in df.columns}
        
        for name in possible_names:
            if name.lower() in df_columns_lower:
                return df_columns_lower[name.lower()]
        
        return None
