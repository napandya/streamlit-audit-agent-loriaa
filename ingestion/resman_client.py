"""
ResMan API Client (stubbed for future implementation)
"""
import requests
from typing import List, Dict, Optional
from datetime import date, datetime
import os

from models.unit import Unit, RecurringTransaction, Lease
from models.canonical_model import CanonicalModel
from utils.helpers import generate_id, is_employee_unit, clean_resident_name
from config import settings


class ResManClient:
    """
    Client for interacting with ResMan API
    Currently stubbed - provides mock data for development
    """
    
    def __init__(self, api_url: str = None, api_key: str = None, property_id: str = None):
        self.api_url = api_url or settings.RESMAN_API_URL
        self.api_key = api_key or settings.RESMAN_API_KEY
        self.property_id = property_id or settings.RESMAN_PROPERTY_ID
        self.session = requests.Session()
        self.authenticated = False
    
    def authenticate(self) -> bool:
        """
        Authenticate with ResMan API
        Currently stubbed - returns True if API key is provided
        """
        if not self.api_key:
            print("Warning: No ResMan API key provided. Using stub mode.")
            return False
        
        # TODO: Implement actual authentication
        # endpoint = f"{self.api_url}/auth"
        # response = self.session.post(endpoint, headers={'X-API-Key': self.api_key})
        # self.authenticated = response.status_code == 200
        
        self.authenticated = True
        return self.authenticated
    
    def fetch_recurring_transactions(
        self,
        start_date: date,
        end_date: date,
        canonical_model: CanonicalModel
    ) -> bool:
        """
        Fetch recurring transactions from ResMan API for date range
        Currently stubbed - generates sample data
        """
        if not self.property_id:
            print("Error: No property ID configured")
            return False
        
        # TODO: Implement actual API call
        # endpoint = f"{self.api_url}/properties/{self.property_id}/recurring-transactions"
        # params = {
        #     'start_date': start_date.isoformat(),
        #     'end_date': end_date.isoformat()
        # }
        # response = self.session.get(endpoint, params=params)
        
        # For now, return stub data
        print(f"Fetching data from ResMan API for {self.property_id}")
        print(f"Date range: {start_date} to {end_date}")
        print("Note: Using stub mode - implement actual API integration")
        
        # Generate sample transactions
        self._generate_stub_data(start_date, end_date, canonical_model)
        
        return True
    
    def fetch_lease_terms(self, canonical_model: CanonicalModel) -> bool:
        """
        Fetch lease terms from ResMan API
        Currently stubbed
        """
        # TODO: Implement actual API call
        print("Fetching lease terms (stub mode)")
        return True
    
    def fetch_unit_details(self, canonical_model: CanonicalModel) -> bool:
        """
        Fetch unit details from ResMan API
        Currently stubbed
        """
        # TODO: Implement actual API call
        print("Fetching unit details (stub mode)")
        return True
    
    def _generate_stub_data(
        self,
        start_date: date,
        end_date: date,
        canonical_model: CanonicalModel
    ):
        """
        Generate stub data for development/testing
        """
        # Sample units
        sample_units = [
            ("0205", "Victoria Braden", False),
            ("0202", "*Clayton Curtis", True),
            ("0301", "Sarah Johnson", False),
        ]
        
        for unit_num, resident, is_employee in sample_units:
            unit = Unit(
                unit_id=f"unit_{unit_num}",
                unit_number=unit_num,
                resident_name=clean_resident_name(resident),
                is_employee_unit=is_employee,
                base_rent=1150.0
            )
            canonical_model.add_unit(unit)
            
            # Generate sample transactions
            current_date = date(start_date.year, start_date.month, 1)
            month_count = 0
            
            while current_date <= end_date and month_count < 12:
                # Base rent
                rent_amount = 1150.0
                if unit_num == "0205" and month_count == 0:
                    rent_amount = 698.0  # Proration example
                
                transaction = RecurringTransaction(
                    transaction_id=generate_id("txn"),
                    unit_id=f"unit_{unit_num}",
                    unit_number=unit_num,
                    category="rent",
                    subcategory=None,
                    amount=rent_amount,
                    month=current_date,
                    description="Rent",
                    source="resman"
                )
                canonical_model.add_transaction(transaction)
                
                # Concession example
                if unit_num == "0205" and month_count == 1:
                    transaction = RecurringTransaction(
                        transaction_id=generate_id("txn"),
                        unit_id=f"unit_{unit_num}",
                        unit_number=unit_num,
                        category="concession",
                        subcategory=None,
                        amount=-1150.0,
                        month=current_date,
                        description="Concession",
                        source="resman"
                    )
                    canonical_model.add_transaction(transaction)
                
                # Employee concession
                if unit_num == "0202":
                    transaction = RecurringTransaction(
                        transaction_id=generate_id("txn"),
                        unit_id=f"unit_{unit_num}",
                        unit_number=unit_num,
                        category="concession",
                        subcategory=None,
                        amount=-676.0,
                        month=current_date,
                        description="Employee Concession",
                        source="resman"
                    )
                    canonical_model.add_transaction(transaction)
                
                # Move to next month
                if current_date.month == 12:
                    current_date = date(current_date.year + 1, 1, 1)
                else:
                    current_date = date(current_date.year, current_date.month + 1, 1)
                
                month_count += 1
