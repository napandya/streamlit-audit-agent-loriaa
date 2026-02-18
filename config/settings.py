"""
Configuration settings for the Village Green Property Audit System
"""
import os
from typing import Dict

# ResMan API Configuration
RESMAN_API_URL = os.getenv("RESMAN_API_URL", "https://api.resman.com/v1")
RESMAN_API_KEY = os.getenv("RESMAN_API_KEY", "")
RESMAN_PROPERTY_ID = os.getenv("RESMAN_PROPERTY_ID", "")

# Application Settings
APP_TITLE = "Village Green Property Audit System"
APP_ICON = "🏢"
DEFAULT_PROPERTY = "Village Green"

# Recurring Fee Template (Standard Village Green Charges)
RECURRING_FEE_TEMPLATE: Dict[str, float] = {
    "Billing Fee": 5.00,
    "Cable": 55.00,
    "CAM": 10.00,
    "HOA": 2.50,
    "Trash": 10.00,
    "Valet Trash": 35.00,
    "Package Locker": 9.00,
    "Pest Control": 8.00,
}

# Audit Rule Thresholds
LEASE_CLIFF_THRESHOLD = 0.20  # 20% revenue drop
EXCESSIVE_CONCESSION_THRESHOLD = 0.50  # 50% of rent
FEE_TOLERANCE = 0.01  # $0.01 tolerance for fee comparison

# Severity Levels
SEVERITY_CRITICAL = "Critical"
SEVERITY_HIGH = "High"
SEVERITY_MEDIUM = "Medium"
SEVERITY_LOW = "Low"

# Export Settings
EXPORT_FORMATS = ["Excel", "CSV", "PDF"]
MAX_UPLOAD_SIZE_MB = 200

# Database Settings
USE_DATABASE = True
DATABASE_PATH = "data/audit.duckdb"

# Date Format
DATE_FORMAT = "%Y-%m-%d"
MONTH_FORMAT = "%Y-%m"

# Employee Unit Marker
EMPLOYEE_UNIT_MARKER = "*"
