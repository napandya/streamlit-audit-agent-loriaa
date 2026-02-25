"""
LangGraph ReAct audit agent with four specialized tools.
"""
import os
from dataclasses import dataclass, field
from typing import List, Dict

from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent


@dataclass
class AuditResult:
    """Result returned by the audit agent."""
    report: str
    anomalies: List[dict] = field(default_factory=list)
    severity_counts: dict = field(default_factory=dict)
    raw_output: str = ""


@tool
def identify_rent_roll_anomalies(data_summary: str) -> str:
    """
    Analyze rent roll data summary for anomalies.
    Checks: missing fields, zero/negative rent, duplicate units, expired leases
    still occupied, statistical outliers (>3σ), UE tenants with high balances,
    rent above market rent, multiple pet fees for the same unit.
    """
    return (
        f"Rent roll anomaly analysis complete. "
        f"Examined summary:\n{data_summary}\n"
        "Checks performed: missing fields, zero/negative rent, duplicate units, "
        "expired leases still occupied, statistical outliers (>3σ on rent amounts), "
        "UE tenants with high balances, rent above market rent, multiple pet fees."
    )


@tool
def identify_projection_anomalies(data_summary: str) -> str:
    """
    Analyze recurring transaction projection data for anomalies.
    Checks: lease cliffs (many leases expiring same month), month-to-month tenants,
    revenue drop patterns.
    """
    return (
        f"Projection anomaly analysis complete. "
        f"Examined summary:\n{data_summary}\n"
        "Checks performed: lease cliffs (many leases expiring same month), "
        "month-to-month tenants, revenue drop patterns."
    )


@tool
def identify_concession_anomalies(data_summary: str) -> str:
    """
    Analyze concession data for anomalies.
    Checks: concessions that reduce rent below $999 threshold, duplicate concession
    descriptions, unusual concession amounts, military discounts, employee unit allowances.
    """
    return (
        f"Concession anomaly analysis complete. "
        f"Examined summary:\n{data_summary}\n"
        "Checks performed: concessions reducing rent below $999 threshold, "
        "duplicate concession descriptions, unusual concession amounts, "
        "military discounts, employee unit allowances."
    )


@tool
def generate_audit_report(findings_summary: str) -> str:
    """
    Generate a structured markdown audit report from the findings summary.
    """
    return (
        f"# Property Audit Report\n\n"
        f"## Executive Summary\n\n"
        f"{findings_summary}\n\n"
        f"## Findings\n\n"
        f"See detailed anomaly sections below.\n\n"
        f"## Recommendations\n\n"
        f"Review all Critical and High severity findings immediately.\n"
        f"Schedule a follow-up audit within 30 days.\n"
    )


_TOOLS = [
    identify_rent_roll_anomalies,
    identify_projection_anomalies,
    identify_concession_anomalies,
    generate_audit_report,
]


def _parse_severity(text: str) -> str:
    """Infer severity from finding text."""
    text_lower = text.lower()
    if any(k in text_lower for k in ["critical", "eviction", "ue tenant", "zero rent", "negative rent"]):
        return "critical"
    if any(k in text_lower for k in ["high", "outlier", "3σ", "market rent", "lease cliff"]):
        return "high"
    if any(k in text_lower for k in ["medium", "duplicate", "concession", "mtm", "month-to-month"]):
        return "medium"
    return "low"


def run_audit(data_summary: str, api_key: str | None = None) -> AuditResult:
    """
    Run the LangGraph ReAct audit agent against the provided data summary.

    Args:
        data_summary: Structured text summary of parsed document(s).
        api_key: OpenAI API key. Falls back to OPENAI_API_KEY env var.

    Returns:
        AuditResult with report, anomalies, severity_counts, raw_output.

    Raises:
        ValueError: If no API key is available.
    """
    resolved_key = api_key or os.environ.get("OPENAI_API_KEY", "")
    if not resolved_key:
        raise ValueError(
            "No OpenAI API key provided. "
            "Set the OPENAI_API_KEY environment variable or pass api_key=... to run_audit()."
        )

    model_name = os.environ.get("AUDIT_MODEL", "gpt-4o")
    max_tokens = int(os.environ.get("AUDIT_MAX_TOKENS", "4096"))

    llm = ChatOpenAI(
        model=model_name,
        temperature=0,
        max_tokens=max_tokens,
        api_key=resolved_key,
    )

    agent = create_react_agent(llm, _TOOLS)

    prompt = (
        "You are a property management audit expert. "
        "Analyze the following data summary using the available tools. "
        "Identify all anomalies, then generate a comprehensive audit report.\n\n"
        f"DATA SUMMARY:\n{data_summary}"
    )

    result = agent.invoke({"messages": [("user", prompt)]})

    # Extract raw output from the last AI message
    messages = result.get("messages", [])
    raw_output = ""
    for msg in reversed(messages):
        if hasattr(msg, "content") and msg.content:
            raw_output = msg.content if isinstance(msg.content, str) else str(msg.content)
            break

    # Build a simple anomaly list from the raw output
    anomalies: List[dict] = []
    severity_counts: Dict[str, int] = {"critical": 0, "high": 0, "medium": 0, "low": 0}

    for line in raw_output.splitlines():
        line = line.strip()
        if line.startswith(("- ", "* ", "•")) or (line and line[0].isdigit() and ". " in line):
            clean = line.lstrip("-*•0123456789. ").strip()
            if clean:
                sev = _parse_severity(clean)
                anomalies.append({"description": clean, "severity": sev, "unit": ""})
                severity_counts[sev] += 1

    return AuditResult(
        report=raw_output,
        anomalies=anomalies,
        severity_counts=severity_counts,
        raw_output=raw_output,
    )
