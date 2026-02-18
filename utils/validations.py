"""
Input validation utilities
"""
from typing import Optional
from datetime import date
import re


def validate_unit_number(unit_number: str) -> bool:
    """Validate unit number format"""
    if not unit_number:
        return False
    
    # Allow alphanumeric unit numbers
    return bool(re.match(r'^[A-Za-z0-9\-]+$', str(unit_number)))


def validate_amount(amount: float) -> bool:
    """Validate monetary amount"""
    try:
        float_amount = float(amount)
        # Allow negative amounts for credits/concessions
        return True
    except (ValueError, TypeError):
        return False


def validate_date_range(start_date: Optional[date], end_date: Optional[date]) -> bool:
    """Validate that date range is logical"""
    if not start_date or not end_date:
        return False
    
    return start_date <= end_date


def validate_severity(severity: str) -> bool:
    """Validate severity level"""
    valid_severities = ['Critical', 'High', 'Medium', 'Low']
    return severity in valid_severities


def validate_status(status: str) -> bool:
    """Validate finding status"""
    valid_statuses = ['Open', 'Reviewed', 'Overridden', 'Closed']
    return status in valid_statuses


def sanitize_filename(filename: str) -> str:
    """Sanitize filename for safe file operations"""
    # Remove or replace unsafe characters
    filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
    # Remove leading/trailing spaces and dots
    filename = filename.strip('. ')
    # Limit length
    if len(filename) > 255:
        filename = filename[:255]
    
    return filename or 'unnamed'


def validate_file_extension(filename: str, allowed_extensions: list) -> bool:
    """Validate file extension"""
    if not filename:
        return False
    
    extension = filename.lower().split('.')[-1]
    return extension in [ext.lower().lstrip('.') for ext in allowed_extensions]
