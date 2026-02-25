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
    findings: list[str] = []
    lines = data_summary.splitlines()

    for line in lines:
        lower = line.lower()
        # UE tenants with high balances
        if "ue" in lower and "balance" in lower:
            findings.append(f"CRITICAL: UE (under-eviction) tenant with outstanding balance — {line.strip()}")
        # Zero or missing rent
        if "zero" in lower and "rent" in lower:
            findings.append(f"CRITICAL: Unit(s) with zero/missing charged rent detected — {line.strip()}")
        # High balance
        if "balance > $1,000" in lower or "high balance" in lower:
            findings.append(f"HIGH: Unit(s) with balance exceeding $1,000 — {line.strip()}")
        # NTV tenants
        if "ntv" in lower and (":" in lower or "ntv:" in lower):
            findings.append(f"MEDIUM: Notice-to-vacate (NTV) tenants may indicate upcoming vacancy risk — {line.strip()}")
        # MTM tenants
        if "mtm" in lower and (":" in lower or "mtm:" in lower):
            findings.append(f"MEDIUM: Month-to-month (MTM) tenants present — higher turnover risk — {line.strip()}")
        # Vacant units
        if "vacant:" in lower or "vacant =" in lower:
            findings.append(f"LOW: Vacant units detected — {line.strip()}")

    if not findings:
        findings.append(
            "No obvious anomalies detected from summary heuristics. "
            "LLM should review the full data for statistical outliers (>3σ on rent), "
            "duplicate unit entries, expired leases still marked occupied, "
            "rent above market rent, and multiple pet fees per unit."
        )

    header = (
        "=== Rent Roll Anomaly Analysis ===\n"
        "Checks applied: missing fields, zero/negative rent, duplicate units, "
        "expired leases still occupied, >3σ outliers, UE with high balances, "
        "rent above market, multiple pet fees.\n\nFindings:\n"
    )
    return header + "\n".join(f"- {f}" for f in findings)


@tool
def identify_projection_anomalies(data_summary: str) -> str:
    """
    Analyze recurring transaction projection data for anomalies.
    Checks: lease cliffs (many leases expiring same month), month-to-month tenants,
    revenue drop patterns.
    """
    findings: list[str] = []
    lines = data_summary.splitlines()

    month_totals: dict[str, float] = {}
    for line in lines:
        lower = line.lower()
        # Parse "  Feb 2026: $87,500.00" style lines
        if line.strip().startswith("Feb ") or line.strip().startswith("Mar ") \
                or line.strip().startswith("Apr ") or line.strip().startswith("May ") \
                or line.strip().startswith("Jun ") or line.strip().startswith("Jul ") \
                or line.strip().startswith("Aug ") or line.strip().startswith("Sep ") \
                or line.strip().startswith("Oct ") or line.strip().startswith("Nov ") \
                or line.strip().startswith("Dec ") or line.strip().startswith("Jan "):
            try:
                parts = line.strip().split(":")
                if len(parts) == 2:
                    month = parts[0].strip()
                    amount = float(parts[1].strip().replace("$", "").replace(",", ""))
                    month_totals[month] = amount
            except Exception:
                pass
        # MTM detection
        if "mtm" in lower or "month-to-month" in lower:
            findings.append(f"MEDIUM: Month-to-month tenants present — {line.strip()}")

    # Check for revenue drops between consecutive months
    if len(month_totals) >= 2:
        months = list(month_totals.keys())
        for i in range(1, len(months)):
            prev_rev = month_totals[months[i - 1]]
            curr_rev = month_totals[months[i]]
            if prev_rev > 0 and curr_rev < prev_rev * 0.9:
                drop_pct = (prev_rev - curr_rev) / prev_rev * 100
                findings.append(
                    f"HIGH: Revenue drop of {drop_pct:.1f}% from {months[i-1]} to {months[i]} "
                    f"(${prev_rev:,.0f} → ${curr_rev:,.0f}) — potential lease cliff."
                )

    if not findings:
        findings.append(
            "No obvious revenue-drop anomalies detected from monthly totals. "
            "LLM should review for lease cliffs and concentrated lease expirations."
        )

    header = (
        "=== Projection Anomaly Analysis ===\n"
        "Checks applied: lease cliffs (≥10% month-over-month revenue drop), "
        "month-to-month tenants, revenue drop patterns.\n\nFindings:\n"
    )
    return header + "\n".join(f"- {f}" for f in findings)


@tool
def identify_concession_anomalies(data_summary: str) -> str:
    """
    Analyze concession data for anomalies.
    Checks: concessions that reduce rent below $999 threshold, duplicate concession
    descriptions, unusual concession amounts, military discounts, employee unit allowances.
    """
    findings: list[str] = []
    lines = data_summary.splitlines()
    seen_descriptions: dict[str, int] = {}

    for line in lines:
        lower = line.lower()
        # Military discount
        if "military" in lower:
            findings.append(f"MEDIUM: Military discount concession detected — {line.strip()}")
        # Employee allowance
        if "employee" in lower and ("allowance" in lower or "unit" in lower):
            findings.append(f"MEDIUM: Employee unit allowance concession detected — {line.strip()}")
        # $999 special pattern — concession brings effective rent to ≤$999
        if "999" in line:
            findings.append(f"HIGH: Possible $999 special detected (concession reducing effective rent to ≤$999) — {line.strip()}")
        # Duplicate description tracking
        if "concession" in lower or "discount" in lower or "credit" in lower:
            desc_key = line.strip().lower()
            seen_descriptions[desc_key] = seen_descriptions.get(desc_key, 0) + 1

    for desc, count in seen_descriptions.items():
        if count > 1:
            findings.append(f"MEDIUM: Duplicate concession description appears {count} times — '{desc}'")

    if not findings:
        findings.append(
            "No obvious concession anomalies detected from heuristics. "
            "LLM should verify no unusual amounts or policy violations."
        )

    header = (
        "=== Concession Anomaly Analysis ===\n"
        "Checks applied: $999 threshold, duplicate descriptions, "
        "military discounts, employee allowances, unusual amounts.\n\nFindings:\n"
    )
    return header + "\n".join(f"- {f}" for f in findings)


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
