"""
Tests for ingestion.loader.FileLoader — routing and error cases.
"""
import os
import tempfile
import pytest

from ingestion.loader import FileLoader
from ingestion.parsers import ParsedDocument


@pytest.fixture
def loader():
    return FileLoader()


# ---------------------------------------------------------------------------
# Extension routing
# ---------------------------------------------------------------------------

def test_load_csv_routes_to_csv_parser(loader, sample_rent_roll_csv_path):
    ok, msg, doc = loader.load_file(sample_rent_roll_csv_path)
    assert ok is True
    assert doc is not None
    assert isinstance(doc, ParsedDocument)
    assert doc.file_type == "csv"


def test_load_pdf_routes_to_pdf_parser(loader, sample_pdf_path):
    ok, msg, doc = loader.load_file(sample_pdf_path)
    assert ok is True
    assert doc is not None
    assert doc.file_type == "pdf"


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------

def test_unsupported_extension_returns_false(loader):
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
        f.write(b"hello")
        tmp = f.name
    try:
        ok, msg, doc = loader.load_file(tmp)
        assert ok is False
        assert doc is None
        assert "Unsupported" in msg or "unsupported" in msg.lower()
    finally:
        os.unlink(tmp)


def test_nonexistent_file_returns_false(loader):
    ok, msg, doc = loader.load_file("/tmp/does_not_exist_xyz.csv")
    assert ok is False
    assert doc is None
    assert "not found" in msg.lower() or "File not found" in msg


def test_backward_compat_returns_three_tuple(loader, sample_rent_roll_csv_path):
    """load_file returns exactly 3 values."""
    result = loader.load_file(sample_rent_roll_csv_path)
    assert len(result) == 3
