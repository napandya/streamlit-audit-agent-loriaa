"""
Anomaly detector orchestrator
"""
from typing import List

from models.unit import Unit, RecurringTransaction, AuditFinding
from engine.rules import RulesEngine


class AnomalyDetector:
    """
    Orchestrates the detection of anomalies across all rules
    """
    
    def __init__(
        self,
        units: List[Unit],
        transactions: List[RecurringTransaction]
    ):
        self.units = units
        self.transactions = transactions
        self.findings: List[AuditFinding] = []
    
    def detect(self) -> List[AuditFinding]:
        """
        Run all anomaly detection rules
        Returns list of findings sorted by severity
        """
        # Create rules engine
        rules_engine = RulesEngine(self.units, self.transactions)
        
        # Run all rules
        self.findings = rules_engine.run_all_rules()
        
        # Sort by severity (Critical > High > Medium > Low)
        severity_order = {
            'Critical': 0,
            'High': 1,
            'Medium': 2,
            'Low': 3
        }
        
        self.findings.sort(key=lambda f: (
            severity_order.get(f.severity, 999),
            f.unit_number,
            f.month or ''
        ))
        
        return self.findings
    
    def get_findings_by_severity(self, severity: str) -> List[AuditFinding]:
        """Get findings filtered by severity level"""
        return [f for f in self.findings if f.severity == severity]
    
    def get_findings_by_unit(self, unit_id: str) -> List[AuditFinding]:
        """Get findings for a specific unit"""
        return [f for f in self.findings if f.unit_id == unit_id]
    
    def get_findings_by_rule(self, rule_id: str) -> List[AuditFinding]:
        """Get findings for a specific rule"""
        return [f for f in self.findings if f.rule_id == rule_id]
    
    def get_summary_stats(self) -> dict:
        """Get summary statistics about findings"""
        total = len(self.findings)
        
        by_severity = {
            'Critical': len([f for f in self.findings if f.severity == 'Critical']),
            'High': len([f for f in self.findings if f.severity == 'High']),
            'Medium': len([f for f in self.findings if f.severity == 'Medium']),
            'Low': len([f for f in self.findings if f.severity == 'Low']),
        }
        
        by_rule = {}
        for finding in self.findings:
            rule = finding.rule_name
            by_rule[rule] = by_rule.get(rule, 0) + 1
        
        affected_units = len(set(f.unit_id for f in self.findings))
        
        return {
            'total_findings': total,
            'by_severity': by_severity,
            'by_rule': by_rule,
            'affected_units': affected_units
        }
