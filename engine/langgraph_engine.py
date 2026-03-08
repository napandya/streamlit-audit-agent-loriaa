"""
LangGraph engine layer — wires the ReAct audit agent into the engine architecture.

Hybrid design:
1. Deterministic ``ConcessionRulesEngine`` pre-scans every concession CSV
   and produces structured findings + per-property stats.
2. Only the pre-scan summary (stats + flagged rows) is sent to the LLM —
   **not** the raw CSV data — which dramatically reduces token usage and
   improves AI accuracy.
3. For non-concession documents (rent rolls, projections) the full summary
   is still sent because those files are already compact.
4. When no API key is available the engine returns the deterministic findings
   alone so the user still gets actionable results.
"""
from typing import Optional, List

import pandas as pd

from models.canonical_model import CanonicalModel
from agents.audit_agent import AuditResult, run_audit
from engine.concession_rules import (
    ConcessionRulesEngine,
    ConcessionFinding,
    PropertyStats,
    format_for_llm,
)
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
        Run the hybrid audit pipeline.

        1. Separate parsed docs into *concession* vs *other* (rent roll / projection).
        2. Run ``ConcessionRulesEngine`` on all concession docs → deterministic
           findings + per-property stats.
        3. Build the LLM summary:
           - Concession docs → ``format_for_llm()`` (stats + flagged rows only).
           - Other docs → full ``DataProcessor.produce_summary()``.
        4. Call the LLM agent with the combined summary.
        5. Merge deterministic findings with LLM findings (dedup by category).

        Returns:
            AuditResult with report, anomalies, severity_counts, raw_output.
        """
        docs = parsed_docs or []

        # --- Split by type ---
        concession_docs: list[ParsedDocument] = []
        other_docs: list[ParsedDocument] = []
        for doc in docs:
            if not isinstance(doc, ParsedDocument):
                continue
            if doc.document_type == "concession":
                concession_docs.append(doc)
            else:
                other_docs.append(doc)

        # --- Step 1: Deterministic concession pre-scan ---
        conc_findings: List[ConcessionFinding] = []
        conc_stats: List[PropertyStats] = []
        if concession_docs:
            engine = ConcessionRulesEngine()
            property_dfs = [
                (doc.file_name, doc.file_name, doc.dataframe)
                for doc in concession_docs
            ]
            conc_findings, conc_stats = engine.run_all(property_dfs)

        # Convert ConcessionFindings to the flat dict format used everywhere
        det_findings = self._concession_findings_to_dicts(conc_findings)

        # Also run the legacy projection checks on non-concession docs
        for doc in other_docs:
            if doc.dataframe is not None and not doc.dataframe.empty:
                det_findings.extend(
                    self._check_projection(doc.dataframe, file_name=doc.file_name)
                )

        # --- Step 2: Build LLM summary ---
        summary_parts: list[str] = []

        # Concession docs → pre-scan summary only (NOT raw CSV rows)
        if conc_findings or conc_stats:
            summary_parts.append(format_for_llm(conc_findings, conc_stats))

        # Other docs → full summary (rent roll, projection, etc.)
        for doc in other_docs:
            summary_parts.append(self._processor.produce_summary(doc))

        # Fallback to canonical model if nothing else
        if not summary_parts:
            summary_parts.append(self._build_canonical_summary(canonical_model))

        if extra_summary:
            summary_parts.append(extra_summary)

        combined_summary = "\n\n".join(summary_parts)

        # --- Step 3: LLM agent ---
        resolved_key = self.api_key
        if resolved_key:
            try:
                llm_result = run_audit(
                    combined_summary,
                    api_key=resolved_key,
                    custom_prompt=custom_prompt,
                )
                return self._merge_results(det_findings, llm_result)
            except Exception:
                pass  # fall through to deterministic-only

        # No API key or LLM call failed — return deterministic findings
        return self._build_deterministic_result(det_findings)

    # ------------------------------------------------------------------
    # Deterministic checks
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Convert ConcessionFinding → flat dict
    # ------------------------------------------------------------------

    @staticmethod
    def _concession_findings_to_dicts(
        findings: List[ConcessionFinding],
    ) -> List[dict]:
        """Convert structured ConcessionFinding objects to the flat dict
        format used by the rest of the pipeline (merge, UI, export)."""
        result: list[dict] = []
        for f in findings:
            result.append({
                "description": f.description,
                "severity": f.severity,
                "unit": ", ".join(f.units[:15]) if f.units else "",
                "source": f.source_file,
                "row": ", ".join(str(r) for r in f.rows[:15]),
                "evidence": f.evidence,
                "rule_id": f.rule_id,
                "reasoning": f.detail,
            })
        return result

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
                # Build detail from actual concession columns
                parts = []
                if "Amount" in df.columns:
                    try:
                        amt = float(str(df.at[idx, "Amount"]).replace(",", "").replace("$", ""))
                        parts.append(f"${amt:,.2f}")
                    except (ValueError, TypeError):
                        pass
                if "Description" in df.columns:
                    desc = str(df.at[idx, "Description"]).strip()
                    if desc and desc != "nan":
                        parts.append(desc)
                if "Name" in df.columns:
                    name = str(df.at[idx, "Name"]).strip()
                    if name and name != "nan":
                        parts.append(name)
                reverse_date = ""
                if "Reverse Date" in df.columns:
                    rd = str(df.at[idx, "Reverse Date"]).strip()
                    if rd and rd not in ("nan", "0", "0.0"):
                        parts.append(f"Reversed: {rd}")
                        reverse_date = rd
                # Fallback to month columns for projection-style data
                if not parts:
                    for mc in month_cols:
                        try:
                            v = float(str(df.at[idx, mc]).replace(",", "").replace("$", ""))
                            if v != 0:
                                parts.append(f"{mc}: ${v:,.2f}")
                        except (ValueError, TypeError):
                            pass
                detail = " | ".join(parts[:4]) if parts else "—"
                concession_hits.append({
                    "unit": unit,
                    "row": int(idx) + 2,
                    "detail": detail,
                    "amount": parts[0] if parts else "",
                    "reversed": reverse_date,
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
