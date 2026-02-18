"""
Helper utility functions
"""
from datetime import datetime, date
from typing import Optional, Union
import re


def format_currency(amount: float) -> str:
    """Format a number as currency"""
    if amount < 0:
        return f"-${abs(amount):,.2f}"
    return f"${amount:,.2f}"


def format_percentage(value: float) -> str:
    """Format a decimal as percentage"""
    return f"{value * 100:.1f}%"


def parse_month(month_str: str) -> Optional[date]:
    """
    Parse various month formats to a date object
    Examples: "Feb 2026", "2026-02", "02/2026"
    """
    if not month_str:
        return None
    
    # Try different formats
    formats = [
        "%b %Y",  # Feb 2026
        "%B %Y",  # February 2026
        "%Y-%m",  # 2026-02
        "%m/%Y",  # 02/2026
        "%Y/%m",  # 2026/02
    ]
    
    for fmt in formats:
        try:
            dt = datetime.strptime(str(month_str).strip(), fmt)
            return date(dt.year, dt.month, 1)
        except ValueError:
            continue
    
    return None


def parse_date(date_str: str) -> Optional[date]:
    """
    Parse various date formats to a date object
    """
    if not date_str:
        return None
    
    if isinstance(date_str, date):
        return date_str
    
    formats = [
        "%Y-%m-%d",  # 2026-02-01
        "%m/%d/%Y",  # 02/01/2026
        "%d/%m/%Y",  # 01/02/2026
        "%Y/%m/%d",  # 2026/02/01
        "%b %d, %Y",  # Feb 01, 2026
        "%B %d, %Y",  # February 01, 2026
    ]
    
    for fmt in formats:
        try:
            return datetime.strptime(str(date_str).strip(), fmt).date()
        except ValueError:
            continue
    
    return None


def parse_currency(amount_str: str) -> float:
    """
    Parse currency string to float
    Examples: "$1,234.56", "($1,234.56)", "-$1,234.56"
    """
    if not amount_str:
        return 0.0
    
    # Convert to string if not already
    amount_str = str(amount_str).strip()
    
    # Handle empty or dash
    if amount_str in ['', '-', 'N/A', 'n/a']:
        return 0.0
    
    # Remove currency symbols and commas
    amount_str = amount_str.replace('$', '').replace(',', '').strip()
    
    # Handle parentheses as negative
    if amount_str.startswith('(') and amount_str.endswith(')'):
        amount_str = '-' + amount_str[1:-1]
    
    try:
        return float(amount_str)
    except ValueError:
        return 0.0


def clean_unit_number(unit_str: str) -> str:
    """
    Clean and standardize unit number
    Examples: "Unit 0205" -> "0205", "#205" -> "0205"
    """
    if not unit_str:
        return ""
    
    # Remove common prefixes
    unit_str = str(unit_str).strip()
    unit_str = re.sub(r'^(Unit|Apt|Apartment|#)\s*', '', unit_str, flags=re.IGNORECASE)
    
    return unit_str.strip()


def is_employee_unit(resident_name: str) -> bool:
    """Check if a resident name indicates an employee unit (marked with *)"""
    if not resident_name:
        return False
    return resident_name.strip().startswith('*')


def clean_resident_name(resident_name: str) -> str:
    """Clean resident name by removing employee marker"""
    if not resident_name:
        return ""
    
    name = resident_name.strip()
    if name.startswith('*'):
        name = name[1:].strip()
    
    return name


def calculate_month_diff(date1: date, date2: date) -> int:
    """Calculate difference in months between two dates"""
    return (date1.year - date2.year) * 12 + (date1.month - date2.month)


def get_month_name(month_date: date) -> str:
    """Get month name from date (e.g., 'Feb 2026')"""
    if not month_date:
        return ""
    return month_date.strftime("%b %Y")


def generate_id(prefix: str = "") -> str:
    """Generate a unique ID"""
    from uuid import uuid4
    unique = str(uuid4())[:8]
    if prefix:
        return f"{prefix}_{unique}"
    return unique
