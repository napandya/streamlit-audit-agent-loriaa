"""
Fee schedules and audit constants for the LiveNjoy ResMan audit system.

Source: Fee sheet .docx files provided by Daniel Twito (March 2026).
All 7 LiveNjoy Residential properties are represented.
"""

# ---------------------------------------------------------------------------
# AUDIT MONTH (update each month before running)
# ---------------------------------------------------------------------------
AUDIT_MONTH = "Mar 2026"

# ---------------------------------------------------------------------------
# APPROVED CONCESSION CODES / DESCRIPTIONS
# ---------------------------------------------------------------------------
APPROVED_CODES = {"CONR", "CRTCO", "EMPL", "MCCR", "RRFee"}

APPROVED_DESCRIPTIONS = {
    "concession - rent",
    "courtesy officer",
    "employee unit rent allowance",
    "miscellaneous credit",
    "resident referral",
}

# ---------------------------------------------------------------------------
# OPTIONAL CHARGE KEYWORDS
# These charge categories are unit-specific add-ons and should not trigger
# the "Missing Standard Charge" (90% rule) — parking, pets, W/D are optional.
# ---------------------------------------------------------------------------
OPTIONAL_CHARGE_KEYWORDS = {
    "carport", "parking", "pet rent", "pet fee", "washer", "dryer",
    "first floor", "1st floor",
}

# ---------------------------------------------------------------------------
# RISK LEVEL LABELS
# ---------------------------------------------------------------------------
RISK_CRITICAL = "CRITICAL"
RISK_HIGH = "HIGH"
RISK_MEDIUM = "MEDIUM"

# ---------------------------------------------------------------------------
# AUDIT THRESHOLDS
# ---------------------------------------------------------------------------
CONCESSION_CRITICAL_AMT = 700      # single credit >= $700 → CRITICAL
CONCESSION_HIGH_AMT = 500          # recurring > $500 for 2+ months → HIGH
STANDARD_CHARGE_THRESHOLD = 0.90   # 90% of units must have a standard charge
RECENT_MOVEIN_DAYS = 60            # move-in within 60 days → $0 rent OK

# ---------------------------------------------------------------------------
# PROPERTY MAP (short code → full name)
# ---------------------------------------------------------------------------
PROPERTY_MAP = {
    "CAI": "Crossings at Irving",
    "POT": "Parks on Taylor",
    "HP": "Highland Park",
    "LP": "La Prada",
    "VG": "Village Green",
    "VPA": "Valencia Plaza",
    "VP": "Valencia Plaza",
    "WST": "Western Station",
}

# ---------------------------------------------------------------------------
# OFFICIAL PER-PROPERTY FEE SCHEDULES
# Source: Daniel Twito's fee sheets (March 2026).
# Structure: property_name → list of fee dicts with keys:
#   name     : human-readable fee name
#   keywords : list of lowercase substrings to match against charge descriptions
#   amount   : expected monthly dollar amount
#   optional : True if the charge is unit-specific (parking, pet, W/D, etc.)
# ---------------------------------------------------------------------------
PROPERTY_FEE_SCHEDULE = {
    "Crossings at Irving": [
        {
            "name": "Billing Fee",
            "keywords": ["billing fee"],
            "amount": 5.00,
            "optional": False,
        },
        {
            "name": "Trash Service",
            "keywords": ["trash service"],
            "amount": 10.00,
            "optional": False,
        },
        {
            "name": "Pest Control",
            "keywords": ["pest control"],
            "amount": 8.00,
            "optional": False,
        },
        {
            "name": "Package Locker",
            "keywords": ["package locker"],
            "amount": 9.00,
            "optional": False,
        },
        {
            "name": "Cable/Internet",
            "keywords": ["cable", "internet"],
            "amount": 55.00,
            "optional": False,
        },
        {
            "name": "First Floor Fee",
            "keywords": ["first floor", "1st floor"],
            "amount": 25.00,
            "optional": True,
        },
        {
            "name": "Washer/Dryer Rental",
            "keywords": ["washer", "dryer"],
            "amount": 55.00,
            "optional": True,
        },
        {
            "name": "Reserved Parking",
            "keywords": ["carport", "parking"],
            "amount": 35.00,
            "optional": True,
        },
        {
            "name": "Pet Rent",
            "keywords": ["pet rent"],
            "amount": 25.00,
            "optional": True,
        },
    ],
    "Highland Park": [
        {
            "name": "Billing Fee",
            "keywords": ["billing fee"],
            "amount": 5.00,
            "optional": False,
        },
        {
            "name": "Trash Service",
            "keywords": ["trash service"],
            "amount": 15.00,
            "optional": False,
        },
        {
            "name": "Pest Control",
            "keywords": ["pest control"],
            "amount": 5.00,
            "optional": False,
        },
        {
            "name": "Community Fee (CAM)",
            "keywords": ["cam", "community fee"],
            "amount": 10.00,
            "optional": True,
        },
        {
            "name": "Valet Trash",
            "keywords": ["valet trash"],
            "amount": 35.00,
            "optional": True,
        },
        {
            "name": "Washer/Dryer Rental",
            "keywords": ["washer", "dryer"],
            "amount": 50.00,
            "optional": True,
        },
        {
            "name": "Reserved Parking",
            "keywords": ["carport", "parking"],
            "amount": 35.00,
            "optional": True,
        },
        {
            "name": "Pet Rent",
            "keywords": ["pet rent"],
            "amount": 15.00,
            "optional": True,
        },
    ],
    "Parks on Taylor": [
        {
            "name": "Billing Fee",
            "keywords": ["billing fee"],
            "amount": 5.00,
            "optional": False,
        },
        {
            "name": "Trash Service",
            "keywords": ["trash service"],
            "amount": 15.00,
            "optional": False,
        },
        {
            "name": "Pest Control",
            "keywords": ["pest control"],
            "amount": 5.00,
            "optional": False,
        },
        {
            "name": "Community Fee (CAM)",
            "keywords": ["cam", "community fee"],
            "amount": 10.00,
            "optional": False,
        },
        {
            "name": "Washer/Dryer Rental",
            "keywords": ["washer", "dryer"],
            "amount": 50.00,
            "optional": True,
        },
        {
            "name": "Reserved Parking",
            "keywords": ["carport", "parking"],
            "amount": 25.00,
            "optional": True,
        },
        {
            "name": "Pet Rent",
            "keywords": ["pet rent"],
            "amount": 20.00,
            "optional": True,
        },
    ],
    "Valencia Plaza": [
        {
            "name": "Billing Fee",
            "keywords": ["billing fee", "utility admin fee"],
            "amount": 5.00,
            "optional": False,
        },
        {
            "name": "Trash Service",
            "keywords": ["trash service"],
            "amount": 10.00,
            "optional": False,
        },
        {
            "name": "Pest Control",
            "keywords": ["pest control"],
            "amount": 6.00,
            "optional": False,
        },
        {
            "name": "Washer/Dryer Rental",
            "keywords": ["washer", "dryer"],
            "amount": 50.00,
            "optional": True,
        },
        {
            "name": "Reserved Parking",
            "keywords": ["carport", "parking"],
            "amount": 35.00,
            "optional": True,
        },
        {
            "name": "Pet Rent",
            "keywords": ["pet rent"],
            "amount": 20.00,
            "optional": True,
        },
    ],
    "Village Green": [
        {
            "name": "Billing Fee",
            "keywords": ["billing fee"],
            "amount": 5.00,
            "optional": False,
        },
        {
            "name": "Trash Service",
            "keywords": ["trash service"],
            "amount": 10.00,
            "optional": False,
        },
        {
            "name": "Pest Control",
            "keywords": ["pest control"],
            "amount": 8.00,
            "optional": False,
        },
        {
            "name": "Community Fee (CAM)",
            "keywords": ["cam", "community fee"],
            "amount": 10.00,
            "optional": False,
        },
        {
            "name": "Valet Trash",
            "keywords": ["valet trash"],
            "amount": 35.00,
            "optional": False,
        },
        {
            "name": "HOA Fee",
            "keywords": ["hoa"],
            "amount": 2.50,
            "optional": False,
        },
        {
            "name": "Package Locker",
            "keywords": ["package locker"],
            "amount": 9.00,
            "optional": False,
        },
        {
            "name": "Cable/Internet",
            "keywords": ["cable", "internet"],
            "amount": 55.00,
            "optional": False,
        },
        {
            "name": "Washer/Dryer Rental",
            "keywords": ["washer", "dryer"],
            "amount": 50.00,
            "optional": True,
        },
        {
            "name": "Carport Rental",
            "keywords": ["carport", "parking"],
            "amount": 35.00,
            "optional": True,
        },
        {
            "name": "Pet Rent",
            "keywords": ["pet rent"],
            "amount": 25.00,
            "optional": True,
        },
    ],
    "Western Station": [
        {
            "name": "Billing Fee",
            "keywords": ["billing fee"],
            "amount": 5.00,
            "optional": False,
        },
        {
            "name": "Trash Service",
            "keywords": ["trash service"],
            "amount": 10.00,
            "optional": False,
        },
        {
            "name": "Pest Control",
            "keywords": ["pest control"],
            "amount": 10.00,
            "optional": False,
        },
        {
            "name": "Community Fee (CAM)",
            "keywords": ["cam", "community fee"],
            "amount": 10.00,
            "optional": False,
        },
        {
            "name": "Valet Trash",
            "keywords": ["valet trash"],
            "amount": 35.00,
            "optional": False,
        },
        {
            "name": "Package Locker",
            "keywords": ["package locker"],
            "amount": 9.00,
            "optional": False,
        },
        {
            "name": "Washer/Dryer Rental",
            "keywords": ["washer", "dryer"],
            "amount": 50.00,
            "optional": True,
        },
        {
            "name": "Reserved Parking",
            "keywords": ["carport", "parking"],
            "amount": 50.00,
            "optional": True,
        },
        {
            "name": "Pet Rent",
            "keywords": ["pet rent"],
            "amount": 25.00,
            "optional": True,
        },
    ],
    "La Prada": [
        {
            "name": "Billing Fee",
            "keywords": ["billing fee"],
            "amount": 5.00,
            "optional": False,
        },
        {
            "name": "Trash Service",
            "keywords": ["trash service"],
            "amount": 10.00,
            "optional": False,
        },
        {
            "name": "Package Locker",
            "keywords": ["package locker"],
            "amount": 7.50,
            "optional": False,
        },
        {
            "name": "Pest Control",
            "keywords": ["pest control"],
            "amount": 6.00,
            "optional": False,
        },
        {
            "name": "Washer/Dryer Rental",
            "keywords": ["washer", "dryer"],
            "amount": 50.00,
            "optional": True,
        },
        {
            "name": "Reserved Parking",
            "keywords": ["carport", "parking"],
            "amount": 35.00,
            "optional": True,
        },
        {
            "name": "Pet Rent",
            "keywords": ["pet rent"],
            "amount": 20.00,
            "optional": True,
        },
    ],
}
