"""
Tests for the ResMan Transaction List parser and ConcessionAuditor rule engine.
"""
from __future__ import annotations

import os
import textwrap
import tempfile

import pandas as pd
import pytest

from ingestion.resman_transaction_parser import parse_resman_transaction_csv
from engine.concession_audit import (
    EXCESSIVE_CONCESSION_THRESHOLD,
    MOVE_IN_SPECIAL_THRESHOLD,
    RULE_META,
    ConcessionAuditor,
    worst_severity,
)


# ---------------------------------------------------------------------------
# Helper — write a minimal synthetic ResMan Transaction List CSV to a temp file
# ---------------------------------------------------------------------------

MINIMAL_RESMAN_CSV = textwrap.dedent(
    """\
    Test Property Apartments,,,,,,,,,,,,,,
    LiveNJoy Residential LLC,,,,,,,,,,,,,,
    Transaction List,,,,,,,,,,,,,,
    February 2026,,,,,,,,,,,,,,
    Printed 3/2/2026 6:00:00 AM,,,,,,,,,,,,,,
    Test Property Apartments,,,,,,,,,,,,,,
    Date,Reference,Unit,Name,Description,Notes,Amount,Gross Payments,Reverse Date,In Period Reversal,Out Of Period Reversal,Period Charges,Prior Charges,Post Charges,Related
    Credit - Concession - Rent,,,,,,,,,,,,,,
    02/01/2026,,101,Alice Smith,Concession - Rent,,500.00,500.00,,,, 500.00,,,RENT
    02/01/2026,,102,Bob Jones,$99 Total M/I,,995.00,995.00,,,,995.00,,,RENT
    02/01/2026,,103,Carol White,Concession - Rent,,1200.00,1200.00,02/15/2026,1200.00,,,,,
    02/01/2026,,104,Dan Brown,One month free,,200.00,200.00,,,,195.50,,4.50,RENT
    Total: 4,,,,,,2895.00,2895.00,,1200.00,,1690.50,,4.50,
    Date,Reference,Unit,Name,Description,Notes,Amount,Gross Payments,Reverse Date,In Period Reversal,Out Of Period Reversal,Period Charges,Prior Charges,Post Charges,Related
    Credit - Courtesy Officer,,,,,,,,,,,,,,
    02/01/2026,,201,Security Staff,Courtesy Officer,,1145.00,1145.00,,,,1145.00,,,RENT
    Total: 1,,,,,,1145.00,1145.00,,,,1145.00,,,
    Date,Reference,Unit,Name,Description,Notes,Amount,Gross Payments,Reverse Date,In Period Reversal,Out Of Period Reversal,Period Charges,Prior Charges,Post Charges,Related
    Credit - Resident Referral,,,,,,,,,,,,,,
    02/05/2026,,301,Jane Doe,Resident Referral,,300.00,300.00,,,,300.00,,,RENT
    Total: 1,,,,,,300.00,300.00,,,,300.00,,,
    """
)


@pytest.fixture
def minimal_resman_csv_path(tmp_path):
    """Write the minimal synthetic ResMan CSV and return its path."""
    csv_file = tmp_path / "Test Transaction List (Credits) - Feb 2026.csv"
    csv_file.write_text(MINIMAL_RESMAN_CSV, encoding="utf-8")
    return str(csv_file)


# ---------------------------------------------------------------------------
# Parser tests
# ---------------------------------------------------------------------------


class TestParseResmanTransactionCsv:
    """Tests for parse_resman_transaction_csv."""

    def test_returns_correct_property_name(self, minimal_resman_csv_path):
        name, _ = parse_resman_transaction_csv(minimal_resman_csv_path)
        assert name == "Test Property Apartments"

    def test_returns_only_concession_rows(self, minimal_resman_csv_path):
        """Non-concession sections (Courtesy Officer, Resident Referral) must be excluded."""
        _, df = parse_resman_transaction_csv(minimal_resman_csv_path)
        # Courtesy Officer (Unit 201) and Resident Referral (Unit 301) should not appear
        assert "201" not in df["Unit"].values
        assert "301" not in df["Unit"].values

    def test_concession_rows_are_present(self, minimal_resman_csv_path):
        _, df = parse_resman_transaction_csv(minimal_resman_csv_path)
        assert set(df["Unit"].tolist()) == {"101", "102", "103", "104"}

    def test_category_column_populated(self, minimal_resman_csv_path):
        _, df = parse_resman_transaction_csv(minimal_resman_csv_path)
        assert "Category" in df.columns
        assert all("Concession" in cat for cat in df["Category"])

    def test_total_and_subheader_rows_dropped(self, minimal_resman_csv_path):
        _, df = parse_resman_transaction_csv(minimal_resman_csv_path)
        assert not any(str(d).startswith("Total:") for d in df["Date"])
        assert not any(str(d).startswith("Credit -") for d in df["Date"])

    def test_repeated_header_rows_dropped(self, minimal_resman_csv_path):
        _, df = parse_resman_transaction_csv(minimal_resman_csv_path)
        assert "Date" not in df["Unit"].values

    def test_amount_numeric(self, minimal_resman_csv_path):
        _, df = parse_resman_transaction_csv(minimal_resman_csv_path)
        assert pd.api.types.is_float_dtype(df["Amount"])
        assert df.loc[df["Unit"] == "102", "Amount"].iloc[0] == 995.0

    def test_post_charges_numeric(self, minimal_resman_csv_path):
        _, df = parse_resman_transaction_csv(minimal_resman_csv_path)
        assert pd.api.types.is_float_dtype(df["Post Charges"])
        assert df.loc[df["Unit"] == "104", "Post Charges"].iloc[0] == 4.5

    def test_reverse_date_filled_as_string(self, minimal_resman_csv_path):
        _, df = parse_resman_transaction_csv(minimal_resman_csv_path)
        # Unit 103 has a reverse date; others should be empty string (not NaN)
        assert df.loc[df["Unit"] == "103", "Reverse Date"].iloc[0] == "02/15/2026"
        assert df.loc[df["Unit"] == "101", "Reverse Date"].iloc[0] == ""

    def test_comma_formatted_amounts_parsed(self, tmp_path):
        """Amount like '1,095.00' must be parsed correctly."""
        csv = (
            "Property A,,,,,,,,,,,,,,\n"
            "LiveNJoy,,,,,,,,,,,,,,\n"
            "Transaction List,,,,,,,,,,,,,,\n"
            "February 2026,,,,,,,,,,,,,,\n"
            "Printed 3/1/2026,,,,,,,,,,,,,,\n"
            "Property A,,,,,,,,,,,,,,\n"
            "Date,Reference,Unit,Name,Description,Notes,Amount,Gross Payments,"
            "Reverse Date,In Period Reversal,Out Of Period Reversal,"
            "Period Charges,Prior Charges,Post Charges,Related\n"
            'Credit - Concession - Rent,,,,,,,,,,,,,,\n'
            '02/01/2026,,0101,Test User,Concession - Rent,,"1,095.00","1,095.00",,,,1095.00,,,RENT\n'
            'Total: 1,,,,,,"1,095.00",1095.00,,,,1095.00,,,\n'
        )
        f = tmp_path / "comma.csv"
        f.write_text(csv, encoding="utf-8")
        _, df = parse_resman_transaction_csv(str(f))
        assert len(df) == 1
        assert df["Amount"].iloc[0] == 1095.0

    def test_latin1_encoding(self, tmp_path):
        """Files with latin-1 encoding (Windows-1252) should be parsed without error."""
        csv_bytes = MINIMAL_RESMAN_CSV.encode("latin-1")
        f = tmp_path / "latin1.csv"
        f.write_bytes(csv_bytes)
        name, df = parse_resman_transaction_csv(str(f))
        assert name == "Test Property Apartments"
        assert not df.empty


# ---------------------------------------------------------------------------
# ConcessionAuditor tests
# ---------------------------------------------------------------------------


def _make_df(**kwargs) -> pd.DataFrame:
    """Build a minimal single-row DataFrame for auditor testing."""
    defaults = {
        "Unit": "101",
        "Description": "Concession - Rent",
        "Amount": 200.0,
        "Reverse Date": "",
        "Post Charges": 0.0,
    }
    defaults.update(kwargs)
    return pd.DataFrame([defaults])


class TestConcessionAuditorRules:
    """Unit tests for each individual audit rule."""

    # --- Rule 1: Reversal Detected (HIGH) ---

    def test_r1_reversal_detected(self):
        df = _make_df(**{"Reverse Date": "02/15/2026"})
        result = ConcessionAuditor(df, "Prop").run()
        assert any("R1" in f for f in result.loc[0, "_anomaly_flags"])
        assert "reversed" in result.loc[0, "_anomaly_reasons"].lower()

    def test_r1_no_reversal_when_empty(self):
        df = _make_df(**{"Reverse Date": ""})
        result = ConcessionAuditor(df, "Prop").run()
        assert not any("R1" in f for f in result.loc[0, "_anomaly_flags"])

    # --- Rule 2: Move-In Special (HIGH) ---

    def test_r2_move_in_special_flagged(self):
        df = _make_df(Amount=MOVE_IN_SPECIAL_THRESHOLD, Description="$99 Total M/I")
        result = ConcessionAuditor(df, "Prop").run()
        assert any("R2" in f for f in result.loc[0, "_anomaly_flags"])

    def test_r2_various_mi_keywords(self):
        for desc in ["Move-In Special Feb", "move in concession", "Free month"]:
            df = _make_df(Amount=900.0, Description=desc)
            result = ConcessionAuditor(df, "Prop").run()
            assert any("R2" in f for f in result.loc[0, "_anomaly_flags"]), (
                f"Expected R2 flag for description: {desc}"
            )

    def test_r2_not_flagged_when_amount_below_threshold(self):
        df = _make_df(Amount=MOVE_IN_SPECIAL_THRESHOLD - 1.0, Description="$99 M/I")
        result = ConcessionAuditor(df, "Prop").run()
        assert not any("R2" in f for f in result.loc[0, "_anomaly_flags"])

    def test_r2_not_flagged_without_mi_keyword(self):
        df = _make_df(Amount=MOVE_IN_SPECIAL_THRESHOLD, Description="Concession - Rent")
        result = ConcessionAuditor(df, "Prop").run()
        assert not any("R2" in f for f in result.loc[0, "_anomaly_flags"])

    # --- Rule 3: Excessive Concession (CRITICAL) ---

    def test_r3_excessive_concession_flagged(self):
        df = _make_df(Amount=EXCESSIVE_CONCESSION_THRESHOLD + 1.0, Description="Concession - Rent")
        result = ConcessionAuditor(df, "Prop").run()
        assert any("R3" in f for f in result.loc[0, "_anomaly_flags"])
        assert any("CRITICAL" in f for f in result.loc[0, "_anomaly_flags"])

    def test_r3_not_flagged_at_exact_threshold(self):
        df = _make_df(Amount=EXCESSIVE_CONCESSION_THRESHOLD, Description="Concession - Rent")
        result = ConcessionAuditor(df, "Prop").run()
        assert not any("R3" in f for f in result.loc[0, "_anomaly_flags"])

    def test_r3_not_flagged_below_threshold(self):
        df = _make_df(Amount=500.0, Description="Concession - Rent")
        result = ConcessionAuditor(df, "Prop").run()
        assert not any("R3" in f for f in result.loc[0, "_anomaly_flags"])

    # --- Rule 4: Post Charges (MEDIUM) ---

    def test_r4_post_charges_flagged(self):
        df = _make_df(**{"Post Charges": 24.50})
        result = ConcessionAuditor(df, "Prop").run()
        assert any("R4" in f for f in result.loc[0, "_anomaly_flags"])

    def test_r4_not_flagged_when_zero(self):
        df = _make_df(**{"Post Charges": 0.0})
        result = ConcessionAuditor(df, "Prop").run()
        assert not any("R4" in f for f in result.loc[0, "_anomaly_flags"])

    # --- Rule 5: Duplicate Unit (MEDIUM) ---

    def test_r5_duplicate_unit_flagged(self):
        df = pd.DataFrame([
            {"Unit": "101", "Description": "Concession - Rent", "Amount": 100.0,
             "Reverse Date": "", "Post Charges": 0.0},
            {"Unit": "101", "Description": "Concession - Rent", "Amount": 200.0,
             "Reverse Date": "", "Post Charges": 0.0},
        ])
        result = ConcessionAuditor(df, "Prop").run()
        assert all(any("R5" in f for f in flags) for flags in result["_anomaly_flags"])

    def test_r5_not_flagged_for_unique_units(self):
        df = pd.DataFrame([
            {"Unit": "101", "Description": "Concession - Rent", "Amount": 100.0,
             "Reverse Date": "", "Post Charges": 0.0},
            {"Unit": "102", "Description": "Concession - Rent", "Amount": 200.0,
             "Reverse Date": "", "Post Charges": 0.0},
        ])
        result = ConcessionAuditor(df, "Prop").run()
        assert not any(any("R5" in f for f in flags) for flags in result["_anomaly_flags"])

    # --- Rule 6: Generic Description (LOW) ---

    def test_r6_generic_description_flagged(self):
        df = _make_df(Description="Concession - Rent")
        result = ConcessionAuditor(df, "Prop").run()
        assert any("R6" in f for f in result.loc[0, "_anomaly_flags"])

    def test_r6_not_flagged_for_descriptive_note(self):
        df = _make_df(Description="One month free prorated over 12 months")
        result = ConcessionAuditor(df, "Prop").run()
        assert not any("R6" in f for f in result.loc[0, "_anomaly_flags"])

    # --- Multi-rule combinations ---

    def test_multiple_rules_can_fire_on_same_row(self):
        """A reversal + excessive amount should fire R1, R3 simultaneously."""
        df = _make_df(
            Amount=EXCESSIVE_CONCESSION_THRESHOLD + 500.0,
            **{"Reverse Date": "02/20/2026"},
        )
        result = ConcessionAuditor(df, "Prop").run()
        flag_ids = {f.split("_")[0] for f in result.loc[0, "_anomaly_flags"]}
        assert "R1" in flag_ids
        assert "R3" in flag_ids

    def test_clean_row_produces_no_flags(self):
        df = _make_df(Amount=200.0, Description="One month free rent", **{"Reverse Date": ""})
        result = ConcessionAuditor(df, "Prop").run()
        assert result.loc[0, "_anomaly_flags"] == []
        assert result.loc[0, "_anomaly_reasons"] == ""


class TestConcessionAuditorSummary:
    """Tests for ConcessionAuditor.summary()."""

    def test_summary_total_rows(self):
        df = pd.DataFrame([
            {"Unit": "101", "Description": "Concession - Rent", "Amount": 200.0,
             "Reverse Date": "", "Post Charges": 0.0},
            {"Unit": "102", "Description": "Concession - Rent", "Amount": 500.0,
             "Reverse Date": "", "Post Charges": 0.0},
        ])
        s = ConcessionAuditor(df, "Prop").summary()
        assert s["total_rows"] == 2

    def test_summary_flagged_rows(self):
        df = pd.DataFrame([
            {"Unit": "101", "Description": "Concession - Rent", "Amount": 1500.0,  # R3
             "Reverse Date": "", "Post Charges": 0.0},
            {"Unit": "102", "Description": "Clean description", "Amount": 100.0,
             "Reverse Date": "", "Post Charges": 0.0},
        ])
        s = ConcessionAuditor(df, "Prop").summary()
        assert s["flagged_rows"] == 1

    def test_summary_critical_count(self):
        df = _make_df(Amount=EXCESSIVE_CONCESSION_THRESHOLD + 1.0, Description="Concession - Rent")
        s = ConcessionAuditor(df, "Prop").summary()
        assert s["severity_counts"]["CRITICAL"] >= 1

    def test_summary_amounts(self):
        df = pd.DataFrame([
            {"Unit": "101", "Description": "Concession - Rent", "Amount": 300.0,
             "Reverse Date": "02/01/2026", "Post Charges": 0.0},  # R1, R6 flagged
            {"Unit": "102", "Description": "Clean description", "Amount": 100.0,
             "Reverse Date": "", "Post Charges": 0.0},  # clean
        ])
        s = ConcessionAuditor(df, "Prop").summary()
        assert s["total_amount"] == pytest.approx(400.0)
        assert s["amount_at_risk"] == pytest.approx(300.0)

    def test_summary_all_severities_present_in_keys(self):
        df = _make_df()
        s = ConcessionAuditor(df, "Prop").summary()
        assert set(s["severity_counts"].keys()) == {"CRITICAL", "HIGH", "MEDIUM", "LOW"}


# ---------------------------------------------------------------------------
# worst_severity helper tests
# ---------------------------------------------------------------------------


class TestWorstSeverity:
    def test_critical_wins(self):
        assert worst_severity(["R6_LOW", "R3_CRITICAL", "R1_HIGH"]) == "CRITICAL"

    def test_high_without_critical(self):
        assert worst_severity(["R1_HIGH", "R6_LOW"]) == "HIGH"

    def test_medium_only(self):
        assert worst_severity(["R5_MEDIUM"]) == "MEDIUM"

    def test_low_only(self):
        assert worst_severity(["R6_LOW"]) == "LOW"

    def test_empty_list_returns_none(self):
        assert worst_severity([]) is None
