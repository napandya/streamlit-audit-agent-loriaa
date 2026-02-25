"""
Pytest fixtures for the audit agent test suite.
"""
import io
import pytest
import pandas as pd
from pathlib import Path

SAMPLES_DIR = Path(__file__).parent.parent / "data" / "samples"


@pytest.fixture
def sample_pdf_path():
    """Path to the sample PDF fixture."""
    p = SAMPLES_DIR / "recurring_transaction_projection.pdf"
    if not p.exists():
        pytest.skip("Sample PDF not found; skipping PDF tests.")
    return str(p)


@pytest.fixture
def sample_rent_roll_csv_path():
    """Path to the sample rent roll CSV fixture."""
    return str(SAMPLES_DIR / "rent_roll_sample.csv")


@pytest.fixture
def sample_projection_csv_path():
    """Path to the sample projection CSV fixture."""
    return str(SAMPLES_DIR / "projection_sample.csv")


@pytest.fixture
def minimal_rent_roll_df():
    """Minimal in-memory DataFrame matching rent roll format."""
    return pd.DataFrame(
        {
            "Unit": ["101", "102", "103", "104", "105"],
            "Type": ["A1", "A1", "A2", "B1", "A3"],
            "Residents": ["Alice", "Bob", "", "Diana", "Eve"],
            "Status": ["C", "NTV", "UE", "Vacant", "MTM"],
            "Market Rent": [1250, 1250, 1400, 1600, 1350],
            "Amount": [1250, 1250, 1400, 0, 1350],
            "Balance": [0, 250, 3200, 0, 0],
        }
    )


@pytest.fixture
def minimal_projection_df():
    """Minimal in-memory DataFrame matching projection format."""
    return pd.DataFrame(
        {
            "Unit Type": ["A1", "A2", "B1"],
            "Description": ["Rent", "Rent", "Rent"],
            "Feb 2026": [87500, 112000, 64000],
            "Mar 2026": [87500, 112000, 64000],
            "Apr 2026": [87500, 112000, 67200],
        }
    )
