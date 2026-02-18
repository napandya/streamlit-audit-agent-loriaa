"""
Explainability layer - generates human-readable explanations for findings
"""
from models.unit import AuditFinding
from utils.helpers import format_currency, format_percentage


class ExplainabilityEngine:
    """
    Generates human-readable explanations for audit findings
    """
    
    @staticmethod
    def explain(finding: AuditFinding) -> str:
        """
        Generate a detailed explanation for a finding
        """
        rule_id = finding.rule_id
        evidence = finding.evidence
        
        if rule_id == "LEASE_CLIFF":
            return ExplainabilityEngine._explain_lease_cliff(finding, evidence)
        elif rule_id == "RENT_PRORATION":
            return ExplainabilityEngine._explain_rent_proration(finding, evidence)
        elif rule_id == "CONCESSION_MISALIGNED":
            return ExplainabilityEngine._explain_concession_misaligned(finding, evidence)
        elif rule_id == "EXCESSIVE_CONCESSION":
            return ExplainabilityEngine._explain_excessive_concession(finding, evidence)
        elif rule_id == "MISSING_RECURRING_CHARGE":
            return ExplainabilityEngine._explain_missing_charges(finding, evidence)
        elif rule_id == "FEE_AMOUNT_MISMATCH":
            return ExplainabilityEngine._explain_fee_mismatch(finding, evidence)
        elif rule_id == "DOUBLE_DISCOUNT":
            return ExplainabilityEngine._explain_double_discount(finding, evidence)
        else:
            return finding.explanation or "No explanation available"
    
    @staticmethod
    def _explain_lease_cliff(finding: AuditFinding, evidence: dict) -> str:
        """Explain lease cliff finding"""
        prev_month = evidence.get('prev_month', 'Unknown')
        prev_rent = evidence.get('prev_rent', 0)
        curr_month = evidence.get('curr_month', 'Unknown')
        curr_rent = evidence.get('curr_rent', 0)
        drop_pct = evidence.get('drop_pct', 0)
        
        return (
            f"Revenue cliff detected in Unit {finding.unit_number}. "
            f"Rent dropped from {format_currency(prev_rent)} in {prev_month} "
            f"to {format_currency(curr_rent)} in {curr_month}, "
            f"a decline of {format_percentage(drop_pct)} ({format_currency(prev_rent - curr_rent)}). "
            f"This indicates a potential lease expiration or renewal issue."
        )
    
    @staticmethod
    def _explain_rent_proration(finding: AuditFinding, evidence: dict) -> str:
        """Explain rent proration mismatch"""
        expected = evidence.get('expected_rent', 0)
        actual = evidence.get('actual_rent', 0)
        month = evidence.get('month', 'Unknown')
        is_lease_start = evidence.get('is_lease_start', False)
        
        if actual < expected:
            if is_lease_start:
                return (
                    f"Unit {finding.unit_number} shows partial rent of {format_currency(actual)} "
                    f"in {month} (expected: {format_currency(expected)}). "
                    f"This appears to be a move-in proration, but verify the move-in date is correct."
                )
            else:
                return (
                    f"Unit {finding.unit_number} charged {format_currency(actual)} in {month}, "
                    f"but expected base rent is {format_currency(expected)}. "
                    f"This is {format_currency(expected - actual)} less than expected. "
                    f"Verify if there's a valid proration or rent adjustment."
                )
        else:
            return (
                f"Unit {finding.unit_number} charged {format_currency(actual)} in {month}, "
                f"which exceeds the base rent of {format_currency(expected)} by {format_currency(actual - expected)}. "
                f"Verify this increase is authorized."
            )
    
    @staticmethod
    def _explain_concession_misaligned(finding: AuditFinding, evidence: dict) -> str:
        """Explain concession misalignment"""
        month = evidence.get('concession_month', 'Unknown')
        amount = evidence.get('concession_amount', 0)
        
        return (
            f"Unit {finding.unit_number} has a concession of {format_currency(amount)} "
            f"in {month}, but no rent charge in that month. "
            f"Concessions should align with the months when rent is charged."
        )
    
    @staticmethod
    def _explain_excessive_concession(finding: AuditFinding, evidence: dict) -> str:
        """Explain excessive concession"""
        month = evidence.get('month', 'Unknown')
        rent = evidence.get('rent', 0)
        concession = evidence.get('concession', 0)
        conc_pct = evidence.get('concession_pct', 0)
        
        return (
            f"Unit {finding.unit_number} has an excessive concession in {month}. "
            f"Rent: {format_currency(rent)}, Concession: {format_currency(concession)} "
            f"({format_percentage(conc_pct)} of rent). "
            f"Concessions exceeding 50% of rent should be reviewed for accuracy."
        )
    
    @staticmethod
    def _explain_missing_charges(finding: AuditFinding, evidence: dict) -> str:
        """Explain missing recurring charges"""
        expected = evidence.get('expected_fees', [])
        
        return (
            f"Unit {finding.unit_number} is missing recurring charges. "
            f"Expected fees include: {', '.join(expected[:5])}{'...' if len(expected) > 5 else ''}. "
            f"Verify if these charges should be applied."
        )
    
    @staticmethod
    def _explain_fee_mismatch(finding: AuditFinding, evidence: dict) -> str:
        """Explain fee amount mismatch"""
        fee_type = evidence.get('fee_type', 'Unknown')
        expected = evidence.get('expected_amount', 0)
        actual = evidence.get('actual_amount', 0)
        month = evidence.get('month', 'Unknown')
        
        diff = actual - expected
        
        return (
            f"Unit {finding.unit_number} has incorrect {fee_type} amount in {month}. "
            f"Expected: {format_currency(expected)}, Actual: {format_currency(actual)} "
            f"(difference: {format_currency(abs(diff))} {'over' if diff > 0 else 'under'}). "
            f"Verify fee schedule is correctly applied."
        )
    
    @staticmethod
    def _explain_double_discount(finding: AuditFinding, evidence: dict) -> str:
        """Explain double discount risk"""
        resident = evidence.get('resident_name', 'Unknown')
        total_conc = evidence.get('total_concessions', 0)
        conc_count = evidence.get('concession_count', 0)
        
        return (
            f"Unit {finding.unit_number} (Resident: {resident}) is marked as an employee unit "
            f"but also has {conc_count} concession(s) totaling {format_currency(total_conc)}. "
            f"This may represent a double discount. Verify that employee allowance and "
            f"promotional concessions are not both applied."
        )
