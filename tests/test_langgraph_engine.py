"""
Tests for engine.langgraph_engine — deterministic checks (no LLM needed).
"""
import pytest
import pandas as pd

from engine.langgraph_engine import LangGraphEngine
from ingestion.parsers import ParsedDocument
from agents.audit_agent import AuditResult


@pytest.fixture
def engine():
    return LangGraphEngine(api_key=None)


def _make_doc(df: pd.DataFrame, doc_type: str = "projection") -> ParsedDocument:
    return ParsedDocument(
        file_name="test.csv",
        file_type="csv",
        raw_text="",
        dataframe=df,
        document_type=doc_type,
    )


# ---------------------------------------------------------------------------
# _check_projection: concessions
# ---------------------------------------------------------------------------

class TestDeterministicConcessions:
    def test_concession_detected(self, engine):
        df = pd.DataFrame({
            "Unit": ["0201", "0201"],
            "Category": ["Rent", "Concession"],
            "Feb 2026": [1250, -200],
            "Mar 2026": [1250, -200],
        })
        findings = engine._check_projection(df)
        conc = [f for f in findings if "concession" in f["description"].lower()]
        assert len(conc) >= 1
        assert conc[0]["severity"] == "medium"

    def test_no_concession_when_absent(self, engine):
        df = pd.DataFrame({
            "Unit": ["0201"],
            "Category": ["Rent"],
            "Feb 2026": [1250],
        })
        findings = engine._check_projection(df)
        conc = [f for f in findings if "concession" in f["description"].lower()]
        assert len(conc) == 0


# ---------------------------------------------------------------------------
# _check_projection: MTM tenants
# ---------------------------------------------------------------------------

class TestDeterministicMTM:
    def test_mtm_detected(self, engine):
        df = pd.DataFrame({
            "Unit": ["0105"],
            "Category": ["Month to Month Fee"],
            "Feb 2026": [150],
        })
        findings = engine._check_projection(df)
        mtm = [f for f in findings if "month-to-month" in f["description"].lower()]
        assert len(mtm) >= 1

    def test_no_mtm_when_absent(self, engine):
        df = pd.DataFrame({
            "Unit": ["0201"],
            "Category": ["Rent"],
            "Feb 2026": [1250],
        })
        findings = engine._check_projection(df)
        mtm = [f for f in findings if "month-to-month" in f["description"].lower()]
        assert len(mtm) == 0


# ---------------------------------------------------------------------------
# _check_projection: revenue cliffs
# ---------------------------------------------------------------------------

class TestDeterministicRevenueCliff:
    def test_revenue_cliff_detected(self, engine):
        df = pd.DataFrame({
            "Unit": ["Property Total"],
            "Category": ["Total"],
            "Feb 2026": [100000],
            "Mar 2026": [85000],  # 15% drop — critical
        })
        findings = engine._check_projection(df)
        cliff = [f for f in findings if "revenue cliff" in f["description"].lower()]
        assert len(cliff) >= 1
        assert cliff[0]["severity"] == "critical"

    def test_no_cliff_when_stable(self, engine):
        df = pd.DataFrame({
            "Unit": ["Property Total"],
            "Category": ["Total"],
            "Feb 2026": [100000],
            "Mar 2026": [99000],
        })
        findings = engine._check_projection(df)
        cliff = [f for f in findings if "revenue cliff" in f["description"].lower()]
        assert len(cliff) == 0


# ---------------------------------------------------------------------------
# _check_projection: employee units
# ---------------------------------------------------------------------------

class TestDeterministicEmployeeUnit:
    def test_employee_unit_detected(self, engine):
        df = pd.DataFrame({
            "Unit": ["0301"],
            "Category": ["Employee Unit Allowance"],
            "Feb 2026": [-500],
        })
        findings = engine._check_projection(df)
        emp = [f for f in findings if "employee" in f["description"].lower()]
        assert len(emp) >= 1


# ---------------------------------------------------------------------------
# run() without API key — deterministic-only
# ---------------------------------------------------------------------------

class TestRunDeterministicOnly:
    def test_returns_audit_result_without_api_key(self, engine):
        from models.canonical_model import CanonicalModel

        df = pd.DataFrame({
            "Unit": ["0201", "0201"],
            "Category": ["Rent", "Concession"],
            "Feb 2026": [1250, -200],
            "Mar 2026": [1250, -200],
        })
        doc = _make_doc(df)
        model = CanonicalModel()
        result = engine.run(model, parsed_docs=[doc])

        assert isinstance(result, AuditResult)
        assert result.severity_counts["medium"] >= 1
        assert any("concession" in a["description"].lower() for a in result.anomalies)
