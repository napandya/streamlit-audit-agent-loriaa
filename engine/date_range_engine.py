"""
Date range filtering and aggregation engine
"""
from datetime import date
from typing import List, Optional, Dict
import pandas as pd

from models.unit import RecurringTransaction


class DateRangeEngine:
    """
    Filters and aggregates recurring transactions by date range
    """
    
    def __init__(self, transactions: List[RecurringTransaction]):
        self.transactions = transactions
    
    def filter_by_date_range(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> List[RecurringTransaction]:
        """Filter transactions within a date range"""
        filtered = self.transactions
        
        if start_date:
            filtered = [t for t in filtered if t.month and t.month >= start_date]
        
        if end_date:
            filtered = [t for t in filtered if t.month and t.month <= end_date]
        
        return filtered
    
    def aggregate_by_month(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> Dict[date, Dict[str, float]]:
        """
        Aggregate transactions by month
        Returns: {month: {'rent': amount, 'concessions': amount, 'fees': amount, 'net': amount}}
        """
        filtered = self.filter_by_date_range(start_date, end_date)
        
        monthly_totals = {}
        
        for txn in filtered:
            if not txn.month:
                continue
            
            if txn.month not in monthly_totals:
                monthly_totals[txn.month] = {
                    'rent': 0.0,
                    'concessions': 0.0,
                    'fees': 0.0,
                    'credits': 0.0,
                    'net': 0.0
                }
            
            if txn.category == 'rent':
                monthly_totals[txn.month]['rent'] += txn.amount
                monthly_totals[txn.month]['net'] += txn.amount
            elif txn.category == 'concession':
                monthly_totals[txn.month]['concessions'] += abs(txn.amount)
                monthly_totals[txn.month]['net'] += txn.amount  # Concessions are negative
            elif txn.category == 'fee':
                monthly_totals[txn.month]['fees'] += txn.amount
                monthly_totals[txn.month]['net'] += txn.amount
            elif txn.category == 'credit':
                monthly_totals[txn.month]['credits'] += abs(txn.amount)
                monthly_totals[txn.month]['net'] += txn.amount  # Credits are negative
        
        return monthly_totals
    
    def aggregate_by_unit(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> Dict[str, Dict[str, float]]:
        """
        Aggregate transactions by unit
        Returns: {unit_id: {'rent': amount, 'concessions': amount, 'fees': amount}}
        """
        filtered = self.filter_by_date_range(start_date, end_date)
        
        unit_totals = {}
        
        for txn in filtered:
            if txn.unit_id not in unit_totals:
                unit_totals[txn.unit_id] = {
                    'unit_number': txn.unit_number,
                    'rent': 0.0,
                    'concessions': 0.0,
                    'fees': 0.0,
                    'credits': 0.0,
                    'net': 0.0,
                    'transaction_count': 0
                }
            
            if txn.category == 'rent':
                unit_totals[txn.unit_id]['rent'] += txn.amount
            elif txn.category == 'concession':
                unit_totals[txn.unit_id]['concessions'] += abs(txn.amount)
            elif txn.category == 'fee':
                unit_totals[txn.unit_id]['fees'] += txn.amount
            elif txn.category == 'credit':
                unit_totals[txn.unit_id]['credits'] += abs(txn.amount)
            
            unit_totals[txn.unit_id]['net'] = (
                unit_totals[txn.unit_id]['rent'] +
                unit_totals[txn.unit_id]['fees'] -
                unit_totals[txn.unit_id]['concessions'] -
                unit_totals[txn.unit_id]['credits']
            )
            unit_totals[txn.unit_id]['transaction_count'] += 1
        
        return unit_totals
    
    def calculate_revenue_trend(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> List[Dict]:
        """
        Calculate month-over-month revenue trend
        Returns list of dicts with month, revenue, change, change_pct
        """
        monthly_totals = self.aggregate_by_month(start_date, end_date)
        
        # Sort by month
        sorted_months = sorted(monthly_totals.keys())
        
        trend = []
        prev_revenue = None
        
        for month in sorted_months:
            revenue = monthly_totals[month]['net']
            
            change = None
            change_pct = None
            
            if prev_revenue is not None:
                change = revenue - prev_revenue
                if prev_revenue != 0:
                    change_pct = change / prev_revenue
                else:
                    change_pct = 0 if revenue == 0 else 1
            
            trend.append({
                'month': month,
                'revenue': revenue,
                'rent': monthly_totals[month]['rent'],
                'concessions': monthly_totals[month]['concessions'],
                'fees': monthly_totals[month]['fees'],
                'change': change,
                'change_pct': change_pct
            })
            
            prev_revenue = revenue
        
        return trend
