"""
Tests for agents.audit_agent — all LLM calls are mocked.
"""
import pytest
from unittest.mock import patch, MagicMock

from agents.audit_agent import (
    AuditResult,
    identify_rent_roll_anomalies,
    identify_projection_anomalies,
    identify_concession_anomalies,
    generate_audit_report,
    run_audit,
)


# ---------------------------------------------------------------------------
# Tool function tests (no LLM needed)
# ---------------------------------------------------------------------------

def test_identify_rent_roll_anomalies_returns_string():
    result = identify_rent_roll_anomalies.invoke({"data_summary": "Unit 101, Status: UE, Balance: $3,200"})
    assert isinstance(result, str)
    assert len(result) > 0


def test_identify_projection_anomalies_returns_string():
    result = identify_projection_anomalies.invoke({"data_summary": "Revenue drop in March 2026"})
    assert isinstance(result, str)


def test_identify_concession_anomalies_returns_string():
    result = identify_concession_anomalies.invoke({"data_summary": "Concession reduces rent to $999"})
    assert isinstance(result, str)


def test_generate_audit_report_returns_string():
    result = generate_audit_report.invoke({"findings_summary": "Found 3 critical issues."})
    assert isinstance(result, str)
    assert "Audit Report" in result


# ---------------------------------------------------------------------------
# AuditResult dataclass
# ---------------------------------------------------------------------------

def test_audit_result_defaults():
    ar = AuditResult(report="Test report")
    assert ar.report == "Test report"
    assert ar.anomalies == []
    assert ar.severity_counts == {}
    assert ar.raw_output == ""


def test_audit_result_with_data():
    ar = AuditResult(
        report="# Report",
        anomalies=[{"description": "zero rent", "severity": "critical", "unit": "101"}],
        severity_counts={"critical": 1, "high": 0, "medium": 0, "low": 0},
        raw_output="raw text",
    )
    assert len(ar.anomalies) == 1
    assert ar.severity_counts["critical"] == 1


# ---------------------------------------------------------------------------
# run_audit — missing API key
# ---------------------------------------------------------------------------

def test_run_audit_missing_api_key():
    """run_audit raises ValueError when no API key is set."""
    import os
    original = os.environ.pop("OPENAI_API_KEY", None)
    try:
        with pytest.raises(ValueError, match="No OpenAI API key"):
            run_audit("some summary", api_key=None)
    finally:
        if original:
            os.environ["OPENAI_API_KEY"] = original


# ---------------------------------------------------------------------------
# run_audit — mocked LangGraph agent
# ---------------------------------------------------------------------------

def test_run_audit_mocked():
    """run_audit returns an AuditResult when the agent is mocked."""
    mock_msg = MagicMock()
    mock_msg.content = "- critical: Unit 101 has zero rent\n- high: Lease cliff in March 2026"

    mock_result = {"messages": [mock_msg]}

    with patch("agents.audit_agent.create_react_agent") as mock_create, \
         patch("agents.audit_agent.ChatOpenAI"):
        mock_agent = MagicMock()
        mock_agent.invoke.return_value = mock_result
        mock_create.return_value = mock_agent

        result = run_audit("Test summary", api_key="sk-fake-key")

    assert isinstance(result, AuditResult)
    assert result.raw_output != ""
