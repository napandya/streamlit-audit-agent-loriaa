"""
Data models for the audit system
"""
from dataclasses import dataclass, field
from datetime import date
from typing import Optional, List


@dataclass
class Unit:
    """Represents a rental unit"""
    unit_id: str
    unit_number: str
    resident_name: Optional[str] = None
    is_employee_unit: bool = False
    lease_start: Optional[date] = None
    lease_end: Optional[date] = None
    base_rent: Optional[float] = None
    
    def __post_init__(self):
        """Detect employee units by asterisk marker"""
        if self.resident_name and self.resident_name.startswith("*"):
            self.is_employee_unit = True
            # Clean the asterisk from name for display
            self.resident_name = self.resident_name.lstrip("*").strip()


@dataclass
class RecurringTransaction:
    """Represents a recurring charge or credit"""
    transaction_id: str
    unit_id: str
    unit_number: str
    category: str  # rent, concession, fee, credit
    subcategory: Optional[str] = None  # billing_fee, cable, etc.
    amount: float = 0.0
    month: Optional[date] = None
    description: Optional[str] = None
    source: str = "unknown"  # pdf, excel, resman
    
    @property
    def is_credit(self) -> bool:
        """Check if this is a credit/concession"""
        return self.amount < 0 or self.category in ['concession', 'credit']
    
    @property
    def is_rent(self) -> bool:
        """Check if this is rent"""
        return self.category == 'rent'
    
    @property
    def is_fee(self) -> bool:
        """Check if this is a recurring fee"""
        return self.category == 'fee'


@dataclass
class Lease:
    """Represents a lease agreement"""
    lease_id: str
    unit_id: str
    unit_number: str
    resident_name: str
    lease_start: date
    lease_end: date
    base_rent: float
    concession_amount: Optional[float] = 0.0
    concession_months: Optional[List[str]] = field(default_factory=list)
    move_in_date: Optional[date] = None
    is_employee_unit: bool = False
    
    @property
    def is_active(self) -> bool:
        """Check if lease is currently active"""
        from datetime import date as dt
        today = dt.today()
        return self.lease_start <= today <= self.lease_end
    
    @property
    def lease_term_months(self) -> int:
        """Calculate lease term in months"""
        months = (self.lease_end.year - self.lease_start.year) * 12
        months += self.lease_end.month - self.lease_start.month
        return months


@dataclass
class AuditFinding:
    """Represents an audit finding/anomaly"""
    finding_id: str
    unit_id: str
    unit_number: str
    rule_id: str
    rule_name: str
    severity: str  # Critical, High, Medium, Low
    month: Optional[date] = None
    delta: Optional[float] = None
    evidence: dict = field(default_factory=dict)
    explanation: str = ""
    status: str = "Open"  # Open, Reviewed, Overridden, Closed
    notes: str = ""
    created_at: Optional[date] = None
    reviewed_at: Optional[date] = None
    reviewed_by: Optional[str] = None
    
    def __post_init__(self):
        """Set created_at if not provided"""
        if self.created_at is None:
            from datetime import date as dt
            self.created_at = dt.today()
