"""
Canonical data model - normalizes data from various sources
"""
from typing import List, Dict, Optional
import pandas as pd
from datetime import datetime
import yaml
from pathlib import Path

from models.unit import Unit, RecurringTransaction, Lease, AuditFinding


class CanonicalModel:
    """
    Canonical data model that normalizes data from various sources
    into a standardized format
    """
    
    def __init__(self):
        self.units: List[Unit] = []
        self.transactions: List[RecurringTransaction] = []
        self.leases: List[Lease] = []
        self.findings: List[AuditFinding] = []
        self._load_mappings()
    
    def _load_mappings(self):
        """Load category mappings from YAML"""
        mappings_path = Path(__file__).parent.parent / "config" / "mappings.yaml"
        try:
            with open(mappings_path, 'r') as f:
                self.mappings = yaml.safe_load(f)
        except FileNotFoundError:
            # Default mappings if file not found
            self.mappings = {
                'rent_categories': ['Rent', 'Base Rent', 'Monthly Rent'],
                'concession_categories': ['Concession', 'Discount'],
                'credit_categories': ['Credit', 'Adjustment'],
            }
    
    def normalize_category(self, description: str) -> tuple[str, Optional[str]]:
        """
        Normalize a charge description to canonical category and subcategory
        Returns: (category, subcategory)
        """
        description_lower = description.lower().strip()
        
        # Check concession categories first (they have higher priority)
        for conc_term in self.mappings.get('concession_categories', []):
            if conc_term.lower() in description_lower:
                return ('concession', None)
        
        # Check credit categories
        for credit_term in self.mappings.get('credit_categories', []):
            if credit_term.lower() in description_lower:
                return ('credit', None)
        
        # Check rent categories
        for rent_term in self.mappings.get('rent_categories', []):
            if rent_term.lower() in description_lower:
                return ('rent', None)
        
        # Check fee categories
        fee_cats = self.mappings.get('fee_categories', {})
        for subcat, terms in fee_cats.items():
            for term in terms:
                if term.lower() in description_lower:
                    return ('fee', subcat)
        
        # Default to 'other'
        return ('other', None)
    
    def add_unit(self, unit: Unit):
        """Add a unit to the model"""
        # Check if unit already exists
        existing = next((u for u in self.units if u.unit_id == unit.unit_id), None)
        if existing:
            # Update existing unit
            existing.resident_name = unit.resident_name or existing.resident_name
            existing.is_employee_unit = unit.is_employee_unit or existing.is_employee_unit
            existing.lease_start = unit.lease_start or existing.lease_start
            existing.lease_end = unit.lease_end or existing.lease_end
            existing.base_rent = unit.base_rent or existing.base_rent
        else:
            self.units.append(unit)
    
    def add_transaction(self, transaction: RecurringTransaction):
        """Add a transaction to the model"""
        self.transactions.append(transaction)
    
    def add_lease(self, lease: Lease):
        """Add a lease to the model"""
        self.leases.append(lease)
    
    def add_finding(self, finding: AuditFinding):
        """Add an audit finding to the model"""
        self.findings.append(finding)
    
    def get_transactions_df(self) -> pd.DataFrame:
        """Get transactions as a pandas DataFrame"""
        if not self.transactions:
            return pd.DataFrame()
        
        data = []
        for t in self.transactions:
            data.append({
                'transaction_id': t.transaction_id,
                'unit_id': t.unit_id,
                'unit_number': t.unit_number,
                'category': t.category,
                'subcategory': t.subcategory,
                'amount': t.amount,
                'month': t.month,
                'description': t.description,
                'source': t.source,
            })
        
        return pd.DataFrame(data)
    
    def get_units_df(self) -> pd.DataFrame:
        """Get units as a pandas DataFrame"""
        if not self.units:
            return pd.DataFrame()
        
        data = []
        for u in self.units:
            data.append({
                'unit_id': u.unit_id,
                'unit_number': u.unit_number,
                'resident_name': u.resident_name,
                'is_employee_unit': u.is_employee_unit,
                'lease_start': u.lease_start,
                'lease_end': u.lease_end,
                'base_rent': u.base_rent,
            })
        
        return pd.DataFrame(data)
    
    def get_findings_df(self) -> pd.DataFrame:
        """Get findings as a pandas DataFrame"""
        if not self.findings:
            return pd.DataFrame()
        
        data = []
        for f in self.findings:
            data.append({
                'finding_id': f.finding_id,
                'unit_id': f.unit_id,
                'unit_number': f.unit_number,
                'rule_id': f.rule_id,
                'rule_name': f.rule_name,
                'severity': f.severity,
                'month': f.month,
                'delta': f.delta,
                'explanation': f.explanation,
                'status': f.status,
                'notes': f.notes,
            })
        
        return pd.DataFrame(data)
    
    def clear(self):
        """Clear all data"""
        self.units.clear()
        self.transactions.clear()
        self.leases.clear()
        self.findings.clear()
