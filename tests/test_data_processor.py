"""
Tests for utils.data_processor.DataProcessor.
"""
import pytest
import pandas as pd

from utils.data_processor import DataProcessor
from ingestion.parsers import ParsedDocument


@pytest.fixture
def processor():
    return DataProcessor()


# ---------------------------------------------------------------------------
# normalize_columns
# ---------------------------------------------------------------------------

class TestNormalizeColumns:
    def test_rent_aliases(self, processor):
        df = pd.DataFrame({"monthly rent": [1250], "unit #": ["101"], "resident": ["Alice"]})
        result = processor.normalize_columns(df)
        assert "monthly_rent" in result.columns
        assert "unit_id" in result.columns
        assert "resident_name" in result.columns

    def test_already_normalized(self, processor):
        df = pd.DataFrame({"monthly_rent": [1250], "unit_id": ["101"]})
        result = processor.normalize_columns(df)
        assert "monthly_rent" in result.columns
        assert "unit_id" in result.columns

    def test_none_input_raises(self, processor):
        with pytest.raises(ValueError):
            processor.normalize_columns(None)

    def test_empty_dataframe(self, processor):
        df = pd.DataFrame()
        result = processor.normalize_columns(df)
        assert result.empty

    def test_balance_alias(self, processor):
        df = pd.DataFrame({"balance": [500]})
        result = processor.normalize_columns(df)
        assert "balance" in result.columns

    def test_deposit_alias(self, processor):
        df = pd.DataFrame({"deposits": [600]})
        result = processor.normalize_columns(df)
        assert "deposit" in result.columns

    def test_move_in_alias(self, processor):
        df = pd.DataFrame({"move in": ["2024-01-01"]})
        result = processor.normalize_columns(df)
        assert "move_in_date" in result.columns


# ---------------------------------------------------------------------------
# produce_summary
# ---------------------------------------------------------------------------

class TestProduceSummary:
    def test_rent_roll_summary(self, processor, minimal_rent_roll_df):
        doc = ParsedDocument(
            file_name="test_rent_roll.csv",
            file_type="csv",
            raw_text="",
            dataframe=minimal_rent_roll_df,
            document_type="rent_roll",
        )
        summary = processor.produce_summary(doc)
        assert isinstance(summary, str)
        assert len(summary) > 0
        assert "Rent Roll" in summary

    def test_projection_summary(self, processor, minimal_projection_df):
        doc = ParsedDocument(
            file_name="test_projection.csv",
            file_type="csv",
            raw_text="",
            dataframe=minimal_projection_df,
            document_type="projection",
        )
        summary = processor.produce_summary(doc)
        assert isinstance(summary, str)
        assert "Projection" in summary

    def test_none_input(self, processor):
        summary = processor.produce_summary(None)
        assert "No document" in summary

    def test_empty_dataframe(self, processor):
        doc = ParsedDocument(
            file_name="empty.csv",
            file_type="csv",
            raw_text="",
            dataframe=pd.DataFrame(),
            document_type="rent_roll",
        )
        summary = processor.produce_summary(doc)
        assert isinstance(summary, str)
        assert len(summary) > 0
