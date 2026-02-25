"""
LangGraph engine layer — wires the ReAct audit agent into the engine architecture.
"""
from typing import List, Optional

from models.canonical_model import CanonicalModel
from agents.audit_agent import AuditResult, run_audit
from utils.data_processor import DataProcessor
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
        # 1. Run deterministic (rule-based) checks on the actual DataFrames.
        deterministic_anomalies = self._run_deterministic_checks(parsed_docs or [])

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

        try:
            llm_result = run_audit(combined_summary, api_key=self.api_key)
            # Combine deterministic findings with LLM findings (deterministic first).
            all_anomalies = deterministic_anomalies + llm_result.anomalies
            severity_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
            for a in all_anomalies:
                sev = a.get("severity", "low")
                severity_counts[sev] = severity_counts.get(sev, 0) + 1
            return AuditResult(
                report=llm_result.report,
                anomalies=all_anomalies,
                severity_counts=severity_counts,
                raw_output=llm_result.raw_output,
            )
        except ValueError:
            # No API key available — return deterministic findings only.
            report = self._format_deterministic_report(deterministic_anomalies)
            severity_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
            for a in deterministic_anomalies:
                sev = a.get("severity", "low")
                severity_counts[sev] = severity_counts.get(sev, 0) + 1
            return AuditResult(
                report=report,
                anomalies=deterministic_anomalies,
                severity_counts=severity_counts,
                raw_output=report,
            )

    # ------------------------------------------------------------------
    # Deterministic (rule-based) checks
    # ------------------------------------------------------------------

    def _run_deterministic_checks(self, parsed_docs: list) -> List[dict]:
        """Run rule-based checks on parsed DataFrames, returning structured anomaly dicts."""
        anomalies: List[dict] = []
        for doc in parsed_docs:
            if not isinstance(doc, ParsedDocument) or doc.dataframe is None or doc.dataframe.empty:
                continue
            if doc.document_type == "projection":
                anomalies.extend(self._check_projection(doc))
            elif doc.document_type == "rent_roll":
                anomalies.extend(self._check_rent_roll(doc))
        return anomalies

    def _check_projection(self, doc: ParsedDocument) -> List[dict]:
        """
        Scan a projection DataFrame for:
        - Recurring concessions (negative amounts in 'Concession' category rows)
        - Month-to-Month tenants (rows with 'Month to Month Fee' category)
        - Revenue cliffs (≥10% MoM drop in Property Total row)
        - Employee unit allowances
        """
        import pandas as pd
        from utils.helpers import parse_month

        anomalies: List[dict] = []
        df = doc.dataframe.copy()

        month_cols = [c for c in df.columns if parse_month(str(c)) is not None]
        if not month_cols:
            return anomalies

        # Locate category and unit columns (case-insensitive)
        cat_col = next((c for c in df.columns if c.lower() == "category"), None)
        unit_col = next((c for c in df.columns if c.lower() == "unit"), None)
        first_col = df.columns[0]

        # --- Concession checks ---
        if cat_col and unit_col:
            conc_mask = (
                df[cat_col].astype(str).str.lower().str.contains("concession", na=False)
            )
            for _, row in df[conc_mask].iterrows():
                unit = str(row.get(unit_col, "")).strip()
                if not unit or unit.lower() == "nan":
                    continue
                monthly_vals = [
                    pd.to_numeric(row.get(c), errors="coerce") for c in month_cols
                ]
                # Only negative amounts indicate concessions
                neg_months = [
                    (c, v)
                    for c, v in zip(month_cols, monthly_vals)
                    if pd.notna(v) and v < 0
                ]
                if not neg_months:
                    continue
                first_month_col, first_amount = neg_months[0]
                last_month_col = neg_months[-1][0]
                anomalies.append({
                    "unit": unit,
                    "description": (
                        f"Recurring concession of ${first_amount:,.2f}/mo "
                        f"(through {last_month_col})"
                    ),
                    "severity": "critical" if abs(first_amount) >= 500 else "high",
                    "category": "Concession",
                })

        # --- Month-to-Month fee checks ---
        if cat_col and unit_col:
            mtm_mask = (
                df[cat_col]
                .astype(str)
                .str.lower()
                .str.contains(r"month to month|mtm fee", na=False)
            )
            for _, row in df[mtm_mask].iterrows():
                unit = str(row.get(unit_col, "")).strip()
                if not unit or unit.lower() == "nan":
                    continue
                active_months = [
                    c for c in month_cols
                    if pd.to_numeric(row.get(c), errors="coerce") > 0
                ]
                if not active_months:
                    continue
                fee_amt = pd.to_numeric(row.get(active_months[0]), errors="coerce")
                anomalies.append({
                    "unit": unit,
                    "description": (
                        f"Month-to-Month tenant — MTM fee ${fee_amt:,.0f}/mo "
                        f"starting {active_months[0]}"
                    ),
                    "severity": "high",
                    "category": "MTM",
                })

        # --- Employee unit checks ---
        if cat_col and unit_col:
            emp_mask = (
                df[cat_col]
                .astype(str)
                .str.lower()
                .str.contains("employee unit", na=False)
            )
            for _, row in df[emp_mask].iterrows():
                unit = str(row.get(unit_col, "")).strip()
                anomalies.append({
                    "unit": unit,
                    "description": "Employee unit with rent allowance credit",
                    "severity": "medium",
                    "category": "Employee Unit",
                })

        # --- Revenue cliff checks (from Property Total row) ---
        total_mask = (
            df[first_col]
            .astype(str)
            .str.lower()
            .str.contains("property total", na=False)
        )
        if total_mask.any():
            total_row = df[total_mask].iloc[0]
            monthly_totals = {
                col: pd.to_numeric(total_row.get(col), errors="coerce")
                for col in month_cols
            }
            months = [m for m in month_cols if pd.notna(monthly_totals.get(m))]
            for i in range(1, len(months)):
                prev_rev = monthly_totals[months[i - 1]]
                curr_rev = monthly_totals[months[i]]
                if prev_rev > 0 and curr_rev < prev_rev * 0.9:
                    drop_pct = (prev_rev - curr_rev) / prev_rev * 100
                    anomalies.append({
                        "unit": "Property Total",
                        "description": (
                            f"Revenue cliff: {months[i-1]} → {months[i]}: "
                            f"${prev_rev:,.0f} → ${curr_rev:,.0f} "
                            f"({drop_pct:.1f}% drop)"
                        ),
                        "severity": "critical" if drop_pct >= 15 else "high",
                        "category": "Lease Cliff",
                    })

        return anomalies

    def _check_rent_roll(self, doc: ParsedDocument) -> List[dict]:
        """Scan a rent roll DataFrame for high-balance and UE anomalies."""
        import pandas as pd

        anomalies: List[dict] = []
        df = self._processor.normalize_columns(doc.dataframe.copy())

        # High balance units
        if "balance" in df.columns and "unit_id" in df.columns:
            unit_df = df.drop_duplicates(subset=["unit_id"], keep="first")
            unit_df = unit_df.copy()
            unit_df["_bal"] = pd.to_numeric(unit_df["balance"], errors="coerce").fillna(0)
            for _, row in unit_df[unit_df["_bal"] > 1000].iterrows():
                anomalies.append({
                    "unit": str(row.get("unit_id", "?")),
                    "description": f"Outstanding balance of ${row['_bal']:,.2f}",
                    "severity": "critical" if row["_bal"] > 3000 else "high",
                    "category": "High Balance",
                })

        return anomalies

    @staticmethod
    def _format_deterministic_report(anomalies: List[dict]) -> str:
        """Format deterministic findings as a simple markdown report."""
        if not anomalies:
            return "# Property Audit Report\n\nNo anomalies detected from rule-based checks."
        lines = ["# Property Audit Report\n", "## Rule-Based Findings\n"]
        for a in anomalies:
            sev = a.get("severity", "low").upper()
            unit = a.get("unit", "")
            desc = a.get("description", "")
            lines.append(f"- **[{sev}]** Unit `{unit}`: {desc}")
        return "\n".join(lines)

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
