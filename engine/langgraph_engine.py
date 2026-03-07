"""
LangGraph engine layer — wires the ReAct audit agent into the engine architecture.

When no OpenAI API key is available the engine falls back to deterministic
DataFrame-driven checks so the user still gets actionable findings.
"""
from typing import Optional, List

import pandas as pd

from models.canonical_model import CanonicalModel
from agents.audit_agent import AuditResult, run_audit, _parse_severity
from utils.data_processor import DataProcessor
from utils.helpers import parse_month
from ingestion.parsers import ParsedDocument


class LangGraphEngine:
    """
    Orchestrates the LangGraph ReAct agent for AI-powered audit analysis.
    Fits the existing engine pattern alongside AnomalyDetector, DateRangeEngine, etc.
    """

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key
        self._processor = DataProcessor()

    def run(
        self,
        canonical_model: CanonicalModel,
        parsed_docs: Optional[list] = None,
        extra_summary: Optional[str] = None,
    ) -> AuditResult:
        """
        Run the LangGraph audit agent.

        Args:
            canonical_model: Populated CanonicalModel instance.
            parsed_docs: Optional list of ParsedDocument objects from the new parsers.
            extra_summary: Optional additional context to include in the prompt.

        Returns:
            AuditResult with report, anomalies, severity_counts, raw_output.
        """
        # Always run deterministic checks regardless of API key availability
        det_findings = self._run_deterministic_checks(parsed_docs or [])

        summary_parts: list[str] = []

        # Build summary from ParsedDocuments if provided
        if parsed_docs:
            for doc in parsed_docs:
                if isinstance(doc, ParsedDocument):
                    summary_parts.append(self._processor.produce_summary(doc))

        # Fallback: build a summary from the canonical model
        if not summary_parts:
            summary_parts.append(self._build_canonical_summary(canonical_model))

        if extra_summary:
            summary_parts.append(extra_summary)

        combined_summary = "\n\n".join(summary_parts)

        # Try the LLM-based agent; fall back to deterministic-only on error
        resolved_key = self.api_key
        if resolved_key:
            try:
                llm_result = run_audit(combined_summary, api_key=resolved_key)
                # Merge deterministic findings into the LLM result
                return self._merge_results(det_findings, llm_result)
            except Exception:
                pass  # fall through to deterministic-only

        # No API key or LLM call failed — return deterministic findings
        return self._build_deterministic_result(det_findings)

    # ------------------------------------------------------------------
    # Deterministic checks
    # ------------------------------------------------------------------

    def _run_deterministic_checks(
        self, parsed_docs: list
    ) -> List[dict]:
        """
        Scan actual DataFrames for concessions, MTM tenants, revenue cliffs,
        and employee-unit rows without needing an LLM.
        """
        findings: List[dict] = []

        for doc in parsed_docs:
            if not isinstance(doc, ParsedDocument):
                continue
            df = doc.dataframe
            if df is None or df.empty:
                continue

            findings.extend(self._check_projection(df))

        return findings

    def _check_projection(self, df: pd.DataFrame) -> List[dict]:
        """Detect concessions, MTM tenants, revenue cliffs, employee units."""
        findings: List[dict] = []

        # Find text column for category / description
        text_col = None
        for candidate in ("Category", "category", "Description", "description"):
            if candidate in df.columns:
                text_col = candidate
                break

        unit_col = None
        for candidate in ("Unit", "unit", "Unit type", "Unit Type"):
            if candidate in df.columns:
                unit_col = candidate
                break

        month_cols = [c for c in df.columns if parse_month(str(c)) is not None]

        if text_col is not None:
            lower_vals = df[text_col].astype(str).str.lower()

            # Concessions
            conc_mask = lower_vals.str.contains("concession", na=False)
            for idx in df.index[conc_mask]:
                unit = df.at[idx, unit_col] if unit_col else "?"
                amounts = []
                for mc in month_cols:
                    try:
                        v = float(str(df.at[idx, mc]).replace(",", "").replace("$", ""))
                        if v != 0:
                            amounts.append(f"{mc}: ${v:,.2f}")
                    except (ValueError, TypeError):
                        pass
                detail = ", ".join(amounts[:3]) if amounts else "see data"
                findings.append({
                    "description": f"Concession on unit {unit} — {detail}",
                    "severity": "medium",
                    "unit": str(unit),
                    "source": "deterministic",
                })

            # MTM tenants
            mtm_mask = lower_vals.str.contains("month to month|mtm", na=False)
            for idx in df.index[mtm_mask]:
                unit = df.at[idx, unit_col] if unit_col else "?"
                findings.append({
                    "description": f"Month-to-month fee on unit {unit}",
                    "severity": "medium",
                    "unit": str(unit),
                    "source": "deterministic",
                })

            # Employee units
            emp_mask = lower_vals.str.contains("employee unit|employee allowance", na=False)
            for idx in df.index[emp_mask]:
                unit = df.at[idx, unit_col] if unit_col else "?"
                findings.append({
                    "description": f"Employee unit detected: {unit}",
                    "severity": "medium",
                    "unit": str(unit),
                    "source": "deterministic",
                })

        # Revenue cliffs (≥10 % MoM drop in Property Total row)
        if month_cols and text_col:
            total_row = None
            for tc in (text_col, unit_col):
                if tc and tc in df.columns:
                    mask = df[tc].astype(str).str.lower().str.contains("property total", na=False)
                    if mask.any():
                        total_row = df.loc[mask]
                        break

            if total_row is not None and not total_row.empty:
                prev_month = None
                prev_val: Optional[float] = None
                for mc in month_cols:
                    cur_val = pd.to_numeric(total_row[mc], errors="coerce").sum()
                    if prev_val is not None and prev_val > 0 and cur_val < prev_val * 0.9:
                        drop_pct = (prev_val - cur_val) / prev_val * 100
                        sev = "critical" if drop_pct >= 15 else "high"
                        findings.append({
                            "description": (
                                f"Revenue cliff: {drop_pct:.1f}% drop from {prev_month} "
                                f"to {mc} (${prev_val:,.0f} → ${cur_val:,.0f})"
                            ),
                            "severity": sev,
                            "unit": "",
                            "source": "deterministic",
                        })
                    prev_month = mc
                    prev_val = cur_val

        return findings

    # ------------------------------------------------------------------
    # Merge / build helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _merge_results(det_findings: List[dict], llm_result: AuditResult) -> AuditResult:
        """Prepend deterministic findings to LLM-generated ones."""
        all_anomalies = det_findings + llm_result.anomalies
        counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        for a in all_anomalies:
            sev = a.get("severity", "low")
            counts[sev] = counts.get(sev, 0) + 1
        return AuditResult(
            report=llm_result.report,
            anomalies=all_anomalies,
            severity_counts=counts,
            raw_output=llm_result.raw_output,
        )

    @staticmethod
    def _build_deterministic_result(det_findings: List[dict]) -> AuditResult:
        """Build an AuditResult from deterministic findings alone."""
        counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        report_lines = ["# Property Audit Report (Deterministic Analysis)\n"]
        for f in det_findings:
            sev = f.get("severity", "low")
            counts[sev] = counts.get(sev, 0) + 1
            report_lines.append(f"- **[{sev.upper()}]** {f['description']}")

        if not det_findings:
            report_lines.append("No anomalies detected from deterministic checks.")

        report = "\n".join(report_lines)
        return AuditResult(
            report=report,
            anomalies=det_findings,
            severity_counts=counts,
            raw_output=report,
        )

    def _build_canonical_summary(self, model: CanonicalModel) -> str:
        """Build a text summary directly from the CanonicalModel."""
        lines: list[str] = ["=== Canonical Model Summary ==="]

        units = model.units
        txns = model.transactions

        lines.append(f"Total units: {len(units)}")
        lines.append(f"Total transactions: {len(txns)}")

        # Unit statuses (basic)
        if units:
            lines.append("\nUnits (first 20):")
            for u in units[:20]:
                lines.append(
                    f"  Unit {u.unit_number} | Resident: {u.resident_name or 'Vacant'} "
                    f"| Employee: {u.is_employee_unit} "
                    f"| Base rent: {u.base_rent}"
                )

        # Transaction summary
        if txns:
            categories = {}
            for t in txns:
                categories[t.category] = categories.get(t.category, 0) + 1
            lines.append(f"\nTransaction categories: {categories}")

        return "\n".join(lines)
