"""
LangGraph engine layer — wires the ReAct audit agent into the engine architecture.

When no OpenAI API key is available the engine falls back to deterministic
DataFrame-driven checks so the user still gets actionable findings.
"""
from typing import Optional, List

import pandas as pd

from models.canonical_model import CanonicalModel
from agents.audit_agent import AuditResult, run_audit
from utils.data_processor import DataProcessor
from utils.helpers import parse_month, find_property_total_row
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
        custom_prompt: Optional[str] = None,
    ) -> AuditResult:
        """
        Run the LangGraph audit agent.

        Args:
            canonical_model: Populated CanonicalModel instance.
            parsed_docs: Optional list of ParsedDocument objects from the new parsers.
            extra_summary: Optional additional context to include in the prompt.
            custom_prompt: Optional user-edited prompt override.

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
                llm_result = run_audit(
                    combined_summary,
                    api_key=resolved_key,
                    custom_prompt=custom_prompt,
                )
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

            findings.extend(self._check_projection(df, file_name=doc.file_name))

        return findings

    def _check_projection(self, df: pd.DataFrame, file_name: str = "") -> List[dict]:
        """Detect concessions, MTM tenants, revenue cliffs, employee units.

        Findings are **aggregated** per pattern per file so the list stays
        concise (like a real auditor would report) while the row-level
        evidence is preserved in the ``evidence`` field.
        """

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

        # Collect raw hits per pattern, then aggregate below
        concession_hits: list[dict] = []
        mtm_hits: list[dict] = []
        employee_hits: list[dict] = []
        findings: List[dict] = []

        if text_col is not None:
            lower_vals = df[text_col].astype(str).str.lower()

            # Concessions
            conc_mask = lower_vals.str.contains("concession", na=False)
            for idx in df.index[conc_mask]:
                unit = str(df.at[idx, unit_col]) if unit_col else "?"
                amounts = []
                for mc in month_cols:
                    try:
                        v = float(str(df.at[idx, mc]).replace(",", "").replace("$", ""))
                        if v != 0:
                            amounts.append(f"{mc}: ${v:,.2f}")
                    except (ValueError, TypeError):
                        pass
                detail = ", ".join(amounts[:3]) if amounts else "see data"
                concession_hits.append({
                    "unit": unit,
                    "row": int(idx) + 2,
                    "detail": detail,
                })

            # MTM tenants
            mtm_mask = lower_vals.str.contains("month to month|mtm", na=False)
            for idx in df.index[mtm_mask]:
                unit = str(df.at[idx, unit_col]) if unit_col else "?"
                mtm_hits.append({"unit": unit, "row": int(idx) + 2})

            # Employee units
            emp_mask = lower_vals.str.contains("employee unit|employee allowance", na=False)
            for idx in df.index[emp_mask]:
                unit = str(df.at[idx, unit_col]) if unit_col else "?"
                employee_hits.append({"unit": unit, "row": int(idx) + 2})

        # --- Aggregate into summary findings ---

        if concession_hits:
            units = sorted({h["unit"] for h in concession_hits})
            rows = sorted({h["row"] for h in concession_hits})
            units_str = ", ".join(units[:10])
            if len(units) > 10:
                units_str += f" … and {len(units) - 10} more"
            findings.append({
                "description": (
                    f"{len(concession_hits)} concession row(s) detected across "
                    f"{len(units)} unit(s): {units_str}"
                ),
                "severity": "medium",
                "unit": units_str,
                "source": file_name or "deterministic",
                "row": ", ".join(str(r) for r in rows[:15]),
                "evidence": concession_hits,
            })

        if mtm_hits:
            units = sorted({h["unit"] for h in mtm_hits})
            rows = sorted({h["row"] for h in mtm_hits})
            findings.append({
                "description": (
                    f"{len(mtm_hits)} month-to-month fee(s) on "
                    f"{len(units)} unit(s): {', '.join(units[:10])}"
                ),
                "severity": "medium",
                "unit": ", ".join(units[:10]),
                "source": file_name or "deterministic",
                "row": ", ".join(str(r) for r in rows[:15]),
                "evidence": mtm_hits,
            })

        if employee_hits:
            units = sorted({h["unit"] for h in employee_hits})
            rows = sorted({h["row"] for h in employee_hits})
            findings.append({
                "description": (
                    f"{len(employee_hits)} employee unit(s) detected: "
                    f"{', '.join(units)}"
                ),
                "severity": "medium",
                "unit": ", ".join(units),
                "source": file_name or "deterministic",
                "row": ", ".join(str(r) for r in rows),
                "evidence": employee_hits,
            })

        # Revenue cliffs (≥10% MoM drop in Property Total row)
        if month_cols and text_col:
            total_row = find_property_total_row(df)

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
                            "source": file_name or "deterministic",
                            "row": "",
                        })
                    prev_month = mc
                    prev_val = cur_val

        return findings

    # ------------------------------------------------------------------
    # Merge / build helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _merge_results(det_findings: List[dict], llm_result: AuditResult) -> AuditResult:
        """Merge deterministic and LLM findings, avoiding duplicates.

        If the LLM already identified a pattern (concession, mtm, employee,
        revenue cliff) that the deterministic check also found, keep the LLM
        version (richer narrative) and attach the deterministic evidence rows.
        """
        # Index deterministic findings by category keyword for dedup
        det_keywords = {
            "concession": [],
            "month-to-month": [],
            "employee": [],
            "revenue cliff": [],
        }
        det_unmatched: list[dict] = []

        for f in det_findings:
            desc_lower = f.get("description", "").lower()
            matched = False
            for kw in det_keywords:
                if kw in desc_lower:
                    det_keywords[kw].append(f)
                    matched = True
                    break
            if not matched:
                det_unmatched.append(f)

        # Check which categories the LLM already covered
        llm_covered: set[str] = set()
        for a in llm_result.anomalies:
            desc_lower = a.get("description", "").lower()
            for kw in det_keywords:
                if kw in desc_lower or kw.replace("-", " ") in desc_lower:
                    llm_covered.add(kw)

        # Only include deterministic findings for categories the LLM missed
        merged: list[dict] = []
        for kw, items in det_keywords.items():
            if kw not in llm_covered:
                merged.extend(items)
        merged.extend(det_unmatched)
        merged.extend(llm_result.anomalies)

        counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        for a in merged:
            sev = a.get("severity", "low")
            counts[sev] = counts.get(sev, 0) + 1

        return AuditResult(
            report=llm_result.report,
            anomalies=merged,
            severity_counts=counts,
            raw_output=llm_result.raw_output,
        )

    @staticmethod
    def _build_deterministic_result(det_findings: List[dict]) -> AuditResult:
        """Build an AuditResult from deterministic findings alone."""
        counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        for f in det_findings:
            sev = f.get("severity", "low")
            counts[sev] = counts.get(sev, 0) + 1

        total = sum(counts.values())

        report_lines = [
            "# Property Audit Report",
            "",
            "## Executive Summary",
            "",
            f"This deterministic scan identified **{total} finding(s)** across the loaded data: "
            f"**{counts['critical']} Critical**, **{counts['high']} High**, "
            f"**{counts['medium']} Medium**, and **{counts['low']} Low** severity items.",
            "",
            "> *Note: This report was generated using rule-based checks only. "
            "Run the AI audit for deeper pattern analysis and narrative explanations.*",
            "",
            "---",
            "",
        ]

        # Group by severity
        sev_labels = [
            ("critical", "🔴 Critical Findings"),
            ("high", "🟠 High Severity Findings"),
            ("medium", "🟡 Medium Severity Findings"),
            ("low", "🟢 Low Severity Findings"),
        ]
        for sev_key, sev_title in sev_labels:
            items = [f for f in det_findings if f.get("severity") == sev_key]
            if items:
                report_lines.append(f"## {sev_title}")
                report_lines.append("")
                for item in items:
                    unit_str = f" (Unit {item['unit']})" if item.get("unit") else ""
                    citation = ""
                    src = item.get("source", "")
                    row = item.get("row", "")
                    if src and row:
                        citation = f" `[Source: {src}, Row {row}]`"
                    elif src:
                        citation = f" `[Source: {src}]`"
                    report_lines.append(f"- **{sev_key.upper()}**{unit_str}: {item['description']}{citation}")
                report_lines.append("")

        if not det_findings:
            report_lines.append("No anomalies detected from deterministic checks.")
            report_lines.append("")

        report_lines += [
            "---",
            "",
            "## Recommendations",
            "",
            "1. Review all Critical and High severity findings with the property manager.",
            "2. Resolve open concession discrepancies and verify reverse-date accuracy.",
            "3. Run the AI audit for deeper analysis and narrative explanations.",
            "",
        ]

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
