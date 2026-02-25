"""
LangGraph engine layer — wires the ReAct audit agent into the engine architecture.
"""
from typing import Optional

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

        return run_audit(combined_summary, api_key=self.api_key)

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
