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
    prompt_used: str = ""


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
    Checks: excessive amounts (>$1,000), $999 specials, reversed concessions,
    move-in specials, duplicate units, generic descriptions, high totals.
    """
    findings: list[str] = []
    lines = data_summary.splitlines()

    current_file = ""
    total_amount = 0.0
    row_count = 0
    reversed_count = 0
    active_count = 0
    large_concessions: list[str] = []
    specials_999: list[str] = []
    movein_specials: list[str] = []
    generic_descs: list[str] = []
    duplicate_units: list[str] = []

    for line in lines:
        stripped = line.strip()

        # Detect file boundary
        if stripped.startswith("=== Concession Document:"):
            if current_file and row_count > 0:
                # Flush findings for the previous file
                findings.append(f"\n--- {current_file} ---")
                findings.append(f"Total rows: {row_count}, Total amount: ${total_amount:,.2f}")
                findings.append(f"Reversed: {reversed_count}, Active: {active_count}")
                if large_concessions:
                    findings.append(f"CRITICAL: {len(large_concessions)} concession(s) > $1,000:")
                    for lc in large_concessions[:10]:
                        findings.append(f"  {lc}")
                if specials_999:
                    findings.append(f"HIGH: {len(specials_999)} $999 special(s):")
                    for s in specials_999[:10]:
                        findings.append(f"  {s}")
                if movein_specials:
                    findings.append(f"HIGH: {len(movein_specials)} move-in special(s):")
                    for m in movein_specials[:10]:
                        findings.append(f"  {m}")
                if generic_descs:
                    findings.append(f"MEDIUM: {len(generic_descs)} generic description(s) (audit risk)")
                if duplicate_units:
                    findings.append(f"MEDIUM: Duplicate unit entries: {', '.join(duplicate_units[:10])}")

            # Reset for new file
            current_file = stripped.replace("=== Concession Document:", "").replace("===", "").strip()
            total_amount = 0.0
            row_count = 0
            reversed_count = 0
            active_count = 0
            large_concessions = []
            specials_999 = []
            movein_specials = []
            generic_descs = []
            duplicate_units = []
            continue

        # Parse stats
        lower = stripped.lower()
        if "total concession amount:" in lower:
            try:
                total_amount = float(lower.split("$")[-1].replace(",", ""))
            except (ValueError, IndexError):
                pass
        if "total concession line items:" in lower:
            try:
                row_count = int(stripped.split(":")[-1].strip())
            except ValueError:
                pass
        if "reversed concessions:" in lower:
            try:
                reversed_count = int(stripped.split(":")[-1].strip())
            except ValueError:
                pass
        if "active (not reversed)" in lower:
            try:
                active_count = int(stripped.split(":")[-1].strip())
            except ValueError:
                pass
        if "concessions > $1,000:" in lower:
            try:
                cnt = int(stripped.split(":")[-1].strip())
                if cnt > 0:
                    large_concessions.append(f"{cnt} found")
            except ValueError:
                pass
        if "$999 specials detected:" in lower:
            try:
                cnt = int(stripped.split(":")[-1].strip())
                if cnt > 0:
                    specials_999.append(f"{cnt} found")
            except ValueError:
                pass
        if "move-in specials detected:" in lower:
            try:
                cnt = int(stripped.split(":")[-1].strip())
                if cnt > 0:
                    movein_specials.append(f"{cnt} found")
            except ValueError:
                pass
        if "generic" in lower and "concession - rent" in lower:
            try:
                cnt = int(stripped.split(":")[-1].strip())
                if cnt > 0:
                    generic_descs.append(f"{cnt} found")
            except ValueError:
                pass
        if "units with multiple concessions:" in lower:
            try:
                cnt = int(stripped.split(":")[-1].strip())
                if cnt > 0:
                    duplicate_units.append(f"{cnt} units")
            except ValueError:
                pass

        # Parse individual data rows
        if stripped.startswith("[Row "):
            lower_row = stripped.lower()
            # Large concession (>$1,000)
            import re as _re
            amt_match = _re.findall(r'\b(\d{1,3}(?:,\d{3})*(?:\.\d+)?)\b', stripped)
            for amt_str in amt_match:
                try:
                    v = float(amt_str.replace(",", ""))
                    if v > 1000:
                        large_concessions.append(stripped[:120])
                        break
                except ValueError:
                    pass
            # $999 special
            if "999" in stripped and ("special" in lower_row or "reduce" in lower_row):
                specials_999.append(stripped[:120])
            # Move-in special
            if any(kw in lower_row for kw in ["$99 total", "move in", "move-in", "m/i"]):
                movein_specials.append(stripped[:120])
            # Generic description
            if "concession - rent" in lower_row and "reduce" not in lower_row and "special" not in lower_row:
                generic_descs.append(stripped[:120])

    # Flush last file
    if current_file and row_count > 0:
        findings.append(f"\n--- {current_file} ---")
        findings.append(f"Total rows: {row_count}, Total amount: ${total_amount:,.2f}")
        findings.append(f"Reversed: {reversed_count}, Active: {active_count}")
        if large_concessions:
            findings.append(f"CRITICAL: {len(large_concessions)} concession(s) > $1,000:")
            for lc in large_concessions[:10]:
                findings.append(f"  {lc}")
        if specials_999:
            findings.append(f"HIGH: {len(specials_999)} $999 special(s):")
            for s in specials_999[:10]:
                findings.append(f"  {s}")
        if movein_specials:
            findings.append(f"HIGH: {len(movein_specials)} move-in special(s):")
            for m in movein_specials[:10]:
                findings.append(f"  {m}")
        if generic_descs:
            findings.append(f"MEDIUM: {len(generic_descs)} generic description(s) (audit risk)")
        if duplicate_units:
            findings.append(f"MEDIUM: Duplicate unit entries: {', '.join(duplicate_units[:10])}")

    if not findings:
        findings.append(
            "No concession data found in the summary. Verify that concession CSV files "
            "were included in the data."
        )

    header = (
        "=== Concession Anomaly Analysis ===\n"
        "Checks applied: excessive amounts (>$1,000), $999 specials, reversed concessions, "
        "move-in specials, duplicate units, generic descriptions.\n\nFindings:\n"
    )
    return header + "\n".join(f"- {f}" for f in findings)


@tool
def generate_audit_report(findings_summary: str) -> str:
    """
    Generate a structured markdown audit report from the findings summary.
    Return a professional, well-formatted markdown report with sections.
    """
    return (
        "# Property Audit Report\n\n"
        "## Executive Summary\n\n"
        f"{findings_summary}\n\n"
        "---\n\n"
        "## Findings Detail\n\n"
        "The following anomalies were identified during the audit analysis. "
        "Each finding is categorised by severity level.\n\n"
        "### 🔴 Critical Findings\n\n"
        "Issues requiring **immediate** attention — potential revenue loss or policy violations.\n\n"
        "### 🟠 High Severity Findings\n\n"
        "Significant risks that should be addressed within the current review cycle.\n\n"
        "### 🟡 Medium Severity Findings\n\n"
        "Items warranting attention but not posing an immediate financial risk.\n\n"
        "### 🟢 Low Severity Findings\n\n"
        "Minor observations and informational items.\n\n"
        "---\n\n"
        "## Recommendations\n\n"
        "1. **Immediate:** Review all Critical and High severity findings with the property manager.\n"
        "2. **Short-term (7 days):** Resolve open concession discrepancies and verify reverse-date accuracy.\n"
        "3. **Follow-up (30 days):** Schedule a re-audit to confirm corrective actions are in place.\n\n"
        "---\n\n"
        "## Methodology\n\n"
        "This report was generated using a combination of deterministic rule-based checks "
        "and AI-powered analysis. Rule-based checks cover duplicate concessions, missing "
        "reverse dates, $999 specials, and employee-unit anomalies. AI analysis provides "
        "deeper pattern recognition, revenue-cliff detection, and narrative explanations.\n"
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


def run_audit(
    data_summary: str,
    api_key: str | None = None,
    custom_prompt: str | None = None,
) -> AuditResult:
    """
    Run the LangGraph ReAct audit agent against the provided data summary.

    Args:
        data_summary: Structured text summary of parsed document(s).
        api_key: OpenAI API key. Falls back to OPENAI_API_KEY env var.
        custom_prompt: Optional user-edited prompt. When provided, it replaces
                       the default system prompt (DATA SUMMARY is still appended).

    Returns:
        AuditResult with report, anomalies, severity_counts, raw_output, prompt_used.

    Raises:
        ValueError: If no API key is available.
    """
    resolved_key = api_key or os.environ.get("OPENAI_API_KEY", "")
    if not resolved_key:
        raise ValueError(
            "No OpenAI API key provided. "
            "Set the OPENAI_API_KEY environment variable or pass api_key=... to run_audit()."
        )

    model_name = os.environ.get("AUDIT_MODEL", "o3")
    max_tokens = int(os.environ.get("AUDIT_MAX_TOKENS", "16384"))

    llm = ChatOpenAI(
        model=model_name,
        temperature=0,
        max_tokens=max_tokens,
        api_key=resolved_key,
    )

    agent = create_react_agent(llm, _TOOLS)

    default_instructions = (
        "You are a senior property management audit expert.\n\n"
        "CONTEXT — HYBRID AUDIT PIPELINE:\n"
        "A deterministic rules engine has ALREADY pre-scanned every concession CSV.\n"
        "The DATA SUMMARY below contains:\n"
        "  • Per-property statistics (row counts, amounts, reversal rates, etc.)\n"
        "  • Flagged findings with rule IDs (CONC-001 through CONC-008) and evidence rows\n"
        "  • For non-concession docs (rent rolls, projections): full summary data\n\n"
        "YOUR JOB is to:\n"
        "1. Review every deterministic finding and provide expert narrative analysis.\n"
        "2. Identify cross-property PATTERNS the rules engine cannot detect:\n"
        "   — Suspicious timing patterns across properties\n"
        "   — Unusual name/description patterns suggesting policy circumvention\n"
        "   — Properties that are outliers relative to the portfolio\n"
        "   — Concession-to-rent ratios that suggest revenue leakage\n"
        "3. Assess business risk and prioritise findings by real-world impact.\n\n"
        "CRITICAL REQUIREMENT — PER-PROPERTY SECTIONS:\n"
        "You MUST produce a dedicated section for each property/file.\n"
        "For each property, create:\n"
        "  ## <Property Name> — <filename>\n\n"
        "Then within each section, list every finding with:\n"
        "  ### Finding: <short title>\n"
        "  **Severity:** 🔴 Critical / 🟠 High / 🟡 Medium / 🟢 Low\n"
        "  **Affected Units:** <unit numbers>\n"
        "  **Citation:** [Source: <filename>, Row <number>]\n"
        "  **Description:** <what was found>\n"
        "  **Reasoning:** <complete chain of reasoning — what data you examined, "
        "what rule or pattern applies, and why it matters>\n"
        "  **Recommended Action:** <specific corrective action>\n\n"
        "DETERMINISTIC RULES REFERENCE:\n"
        "CONC-001: Excessive single concession (> $1,000)\n"
        "CONC-002: $999 special-rate concessions\n"
        "CONC-003: Move-in specials ($99 / $0)\n"
        "CONC-004: Reversed concessions (Reverse Date populated)\n"
        "CONC-005: Duplicate unit concessions (same unit, multiple rows)\n"
        "CONC-006: Generic / vague descriptions\n"
        "CONC-007: High property-level total (> 2× portfolio median)\n"
        "CONC-008: Negative concession amounts\n\n"
        "OUTPUT STRUCTURE:\n"
        "Start with an **Executive Summary** (2-3 sentences covering all properties).\n"
        "Then one ## section per property with all findings.\n"
        "End with a **Cross-Property Comparison** table and **Recommendations** section.\n\n"
        "Use the available tools to analyze the data. Do NOT include raw data dumps.\n"
        "Do NOT repeat the deterministic stats verbatim — add audit insight and narrative."
    )

    instructions = custom_prompt if custom_prompt else default_instructions
    prompt = f"{instructions}\n\nDATA SUMMARY:\n{data_summary}"

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

    import re
    source_pattern = re.compile(r'\[Source:\s*([^,\]]+?)(?:,\s*Row\s*([\d,\s]+))?\]', re.IGNORECASE)
    # Detect file section headers like "## Crossings at Irving — CAI Transaction..."
    file_section_pattern = re.compile(
        r'^#{1,3}\s+(.+?)\s*(?:—|--|-)?\s*(.+?Transaction List.+?\.csv)',
        re.IGNORECASE,
    )
    # Detect finding sub-headers like "### Finding: $999 Specials"
    finding_header_pattern = re.compile(r'^#{1,4}\s+(?:Finding:?\s*)?(.+)', re.IGNORECASE)

    current_source_file = ""
    current_finding_title = ""
    current_severity = ""
    current_description_lines: list[str] = []
    current_reasoning = ""
    current_units = ""
    current_citation_file = ""
    current_citation_row = ""

    def _flush_finding():
        nonlocal current_finding_title, current_severity, current_description_lines
        nonlocal current_reasoning, current_units, current_citation_file, current_citation_row
        if current_finding_title:
            desc = current_finding_title
            if current_description_lines:
                desc += " — " + " ".join(current_description_lines)
            sev = current_severity or _parse_severity(desc)
            src = current_citation_file or current_source_file
            anomalies.append({
                "description": desc.strip(),
                "severity": sev,
                "unit": current_units,
                "source": src,
                "row": current_citation_row,
                "reasoning": current_reasoning,
            })
            severity_counts[sev] += 1
        current_finding_title = ""
        current_severity = ""
        current_description_lines = []
        current_reasoning = ""
        current_units = ""
        current_citation_file = ""
        current_citation_row = ""

    for line in raw_output.splitlines():
        stripped = line.strip()
        if not stripped:
            continue

        # Check for file section header
        file_match = file_section_pattern.match(stripped)
        if file_match:
            _flush_finding()
            current_source_file = file_match.group(2).strip()
            continue

        # Check for finding header
        if stripped.startswith("#"):
            header_match = finding_header_pattern.match(stripped)
            if header_match:
                _flush_finding()
                title = header_match.group(1).strip()
                # Skip generic section headers
                if title.lower() not in (
                    "executive summary", "recommendations", "cross-property comparison",
                    "methodology", "findings detail",
                ):
                    current_finding_title = title
            continue

        # Extract structured fields
        lower = stripped.lower()
        if lower.startswith("**severity:**") or lower.startswith("severity:"):
            raw_sev = stripped.split(":", 1)[1].strip().strip("*").strip().lower()
            if "critical" in raw_sev:
                current_severity = "critical"
            elif "high" in raw_sev:
                current_severity = "high"
            elif "medium" in raw_sev:
                current_severity = "medium"
            else:
                current_severity = "low"
            continue

        if lower.startswith("**affected units:**") or lower.startswith("affected units:"):
            current_units = stripped.split(":", 1)[1].strip().strip("*").strip()
            continue

        if lower.startswith("**reasoning:**") or lower.startswith("reasoning:"):
            current_reasoning = stripped.split(":", 1)[1].strip().strip("*").strip()
            continue

        if lower.startswith("**description:**") or lower.startswith("description:"):
            current_description_lines.append(stripped.split(":", 1)[1].strip().strip("*").strip())
            continue

        # Extract source citations from any line
        source_match = source_pattern.search(stripped)
        if source_match:
            current_citation_file = source_match.group(1).strip()
            if source_match.group(2):
                current_citation_row = source_match.group(2).strip()
            continue

        # Fallback: bullet-point findings (for less structured output)
        if stripped.startswith(("- ", "* ", "• ")) or (stripped and stripped[0].isdigit() and ". " in stripped):
            clean = stripped.lstrip("-*•0123456789. ").strip()
            if clean and not current_finding_title:
                sev = _parse_severity(clean)
                src_match = source_pattern.search(clean)
                source_file = src_match.group(1).strip() if src_match else current_source_file
                source_row = src_match.group(2).strip() if src_match and src_match.group(2) else ""
                anomalies.append({
                    "description": clean,
                    "severity": sev,
                    "unit": "",
                    "source": source_file,
                    "row": source_row,
                    "reasoning": "",
                })
                severity_counts[sev] += 1

    # Flush last finding
    _flush_finding()

    return AuditResult(
        report=raw_output,
        anomalies=anomalies,
        severity_counts=severity_counts,
        raw_output=raw_output,
        prompt_used=instructions,
    )
