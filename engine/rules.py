"""
Validation rules engine - implements all audit rules
"""
from typing import List, Dict, Optional
from datetime import date
from collections import defaultdict

from models.unit import Unit, RecurringTransaction, AuditFinding
from config import settings
from utils.helpers import generate_id


class RulesEngine:
    """
    Implements all validation rules for the audit system
    """
    
    def __init__(
        self,
        units: List[Unit],
        transactions: List[RecurringTransaction]
    ):
        self.units = units
        self.transactions = transactions
        self.findings: List[AuditFinding] = []
        
        # Build indexes for faster lookups
        self.units_by_id = {u.unit_id: u for u in units}
        self.transactions_by_unit = defaultdict(list)
        for txn in transactions:
            self.transactions_by_unit[txn.unit_id].append(txn)
    
    def run_all_rules(self) -> List[AuditFinding]:
        """Run all validation rules and return findings"""
        self.findings = []
        
        # Rule A: Lease Cliff Detection
        self.check_lease_cliff()
        
        # Rule B: Concession Misalignment
        self.check_rent_proration_mismatch()
        self.check_concession_misalignment()
        self.check_excessive_concession()
        
        # Rule C: Recurring Fee Template Validation
        self.check_missing_recurring_charges()
        self.check_fee_amount_mismatch()
        
        # Rule D: Employee Unit vs Concession Conflict
        self.check_double_discount()
        
        return self.findings
    
    def check_lease_cliff(self):
        """
        Rule A: Lease Cliff Detection
        IF monthly_rent_drop > 20% FLAG: LEASE_CLIFF_RISK
        """
        # Group transactions by unit and month
        unit_monthly_rent = defaultdict(lambda: defaultdict(float))
        
        for txn in self.transactions:
            if txn.category == 'rent' and txn.month:
                unit_monthly_rent[txn.unit_id][txn.month] += txn.amount
        
        # Check each unit for revenue drops
        for unit_id, monthly_rents in unit_monthly_rent.items():
            sorted_months = sorted(monthly_rents.keys())
            
            for i in range(1, len(sorted_months)):
                prev_month = sorted_months[i - 1]
                curr_month = sorted_months[i]
                
                prev_rent = monthly_rents[prev_month]
                curr_rent = monthly_rents[curr_month]
                
                if prev_rent > 0:
                    drop_pct = (prev_rent - curr_rent) / prev_rent
                    
                    if drop_pct > settings.LEASE_CLIFF_THRESHOLD:
                        unit = self.units_by_id.get(unit_id)
                        finding = AuditFinding(
                            finding_id=generate_id("finding"),
                            unit_id=unit_id,
                            unit_number=unit.unit_number if unit else unit_id,
                            rule_id="LEASE_CLIFF",
                            rule_name="Lease Cliff Risk",
                            severity=settings.SEVERITY_CRITICAL if drop_pct > 0.5 else settings.SEVERITY_HIGH,
                            month=curr_month,
                            delta=-1 * (prev_rent - curr_rent),
                            evidence={
                                'prev_month': prev_month.strftime('%b %Y'),
                                'prev_rent': prev_rent,
                                'curr_month': curr_month.strftime('%b %Y'),
                                'curr_rent': curr_rent,
                                'drop_pct': drop_pct
                            }
                        )
                        self.findings.append(finding)
    
    def check_rent_proration_mismatch(self):
        """
        Rule B1: Rent Proration Mismatch
        IF rent_amount != lease_contract_rent AND no valid proration
        FLAG: RENT_PRORATION_MISMATCH
        """
        for unit in self.units:
            if not unit.base_rent:
                continue
            
            unit_txns = self.transactions_by_unit[unit.unit_id]
            rent_txns = [t for t in unit_txns if t.category == 'rent']
            
            for txn in rent_txns:
                # Check if rent differs from base rent
                if abs(txn.amount - unit.base_rent) > 1.0:  # Allow $1 tolerance
                    # Check if it's a valid proration (first month of lease)
                    is_proration = (
                        unit.lease_start and
                        txn.month and
                        txn.month.year == unit.lease_start.year and
                        txn.month.month == unit.lease_start.month
                    )
                    
                    # If it's less than base rent and not first month, flag it
                    if not is_proration or txn.amount > unit.base_rent:
                        finding = AuditFinding(
                            finding_id=generate_id("finding"),
                            unit_id=unit.unit_id,
                            unit_number=unit.unit_number,
                            rule_id="RENT_PRORATION",
                            rule_name="Rent Proration Mismatch",
                            severity=settings.SEVERITY_MEDIUM,
                            month=txn.month,
                            delta=txn.amount - unit.base_rent,
                            evidence={
                                'expected_rent': unit.base_rent,
                                'actual_rent': txn.amount,
                                'month': txn.month.strftime('%b %Y') if txn.month else 'Unknown',
                                'is_lease_start': is_proration
                            }
                        )
                        self.findings.append(finding)
    
    def check_concession_misalignment(self):
        """
        Rule B2: Concession Misalignment
        IF concession_month NOT aligned with lease incentive
        FLAG: CONCESSION_MISALIGNED
        """
        for unit in self.units:
            unit_txns = self.transactions_by_unit[unit.unit_id]
            rent_txns = [t for t in unit_txns if t.category == 'rent']
            conc_txns = [t for t in unit_txns if t.category == 'concession']
            
            # Check if concessions appear in months without rent
            rent_months = {t.month for t in rent_txns if t.month}
            
            for conc in conc_txns:
                if conc.month and conc.month not in rent_months:
                    finding = AuditFinding(
                        finding_id=generate_id("finding"),
                        unit_id=unit.unit_id,
                        unit_number=unit.unit_number,
                        rule_id="CONCESSION_MISALIGNED",
                        rule_name="Concession Misaligned",
                        severity=settings.SEVERITY_MEDIUM,
                        month=conc.month,
                        delta=conc.amount,
                        evidence={
                            'concession_month': conc.month.strftime('%b %Y'),
                            'concession_amount': abs(conc.amount),
                            'has_rent_in_month': False
                        }
                    )
                    self.findings.append(finding)
    
    def check_excessive_concession(self):
        """
        Rule B3: Excessive Concession
        IF concession_amount > 50% of rent
        FLAG: EXCESSIVE_CONCESSION
        """
        for unit in self.units:
            unit_txns = self.transactions_by_unit[unit.unit_id]
            
            # Group by month
            monthly_data = defaultdict(lambda: {'rent': 0, 'concession': 0})
            
            for txn in unit_txns:
                if txn.month:
                    if txn.category == 'rent':
                        monthly_data[txn.month]['rent'] += txn.amount
                    elif txn.category == 'concession':
                        monthly_data[txn.month]['concession'] += abs(txn.amount)
            
            # Check each month
            for month, data in monthly_data.items():
                if data['rent'] > 0:
                    conc_pct = data['concession'] / data['rent']
                    
                    if conc_pct > settings.EXCESSIVE_CONCESSION_THRESHOLD:
                        finding = AuditFinding(
                            finding_id=generate_id("finding"),
                            unit_id=unit.unit_id,
                            unit_number=unit.unit_number,
                            rule_id="EXCESSIVE_CONCESSION",
                            rule_name="Excessive Concession",
                            severity=settings.SEVERITY_HIGH,
                            month=month,
                            delta=-data['concession'],
                            evidence={
                                'month': month.strftime('%b %Y'),
                                'rent': data['rent'],
                                'concession': data['concession'],
                                'concession_pct': conc_pct
                            }
                        )
                        self.findings.append(finding)
    
    def check_missing_recurring_charges(self):
        """
        Rule C1: Missing Recurring Charge
        IF recurring_fee_missing AND lease_active
        FLAG: MISSING_RECURRING_CHARGE
        """
        # This rule requires knowledge of expected fees per property
        # For now, we'll check if units have any fees at all
        for unit in self.units:
            unit_txns = self.transactions_by_unit[unit.unit_id]
            fee_txns = [t for t in unit_txns if t.category == 'fee']
            
            # If unit has rent but no fees, flag it
            rent_txns = [t for t in unit_txns if t.category == 'rent']
            
            if rent_txns and not fee_txns:
                finding = AuditFinding(
                    finding_id=generate_id("finding"),
                    unit_id=unit.unit_id,
                    unit_number=unit.unit_number,
                    rule_id="MISSING_RECURRING_CHARGE",
                    rule_name="Missing Recurring Charges",
                    severity=settings.SEVERITY_LOW,
                    month=None,
                    delta=None,
                    evidence={
                        'expected_fees': list(settings.RECURRING_FEE_TEMPLATE.keys()),
                        'actual_fees': []
                    }
                )
                self.findings.append(finding)
    
    def check_fee_amount_mismatch(self):
        """
        Rule C2: Fee Amount Mismatch
        IF recurring_fee_amount != template_amount
        FLAG: FEE_AMOUNT_MISMATCH
        """
        for txn in self.transactions:
            if txn.category == 'fee' and txn.subcategory:
                # Map subcategory to template fee name
                template_name = self._map_fee_to_template(txn.subcategory)
                
                if template_name and template_name in settings.RECURRING_FEE_TEMPLATE:
                    expected_amount = settings.RECURRING_FEE_TEMPLATE[template_name]
                    
                    if abs(txn.amount - expected_amount) > settings.FEE_TOLERANCE:
                        unit = self.units_by_id.get(txn.unit_id)
                        finding = AuditFinding(
                            finding_id=generate_id("finding"),
                            unit_id=txn.unit_id,
                            unit_number=unit.unit_number if unit else txn.unit_number,
                            rule_id="FEE_AMOUNT_MISMATCH",
                            rule_name="Fee Amount Mismatch",
                            severity=settings.SEVERITY_LOW,
                            month=txn.month,
                            delta=txn.amount - expected_amount,
                            evidence={
                                'fee_type': template_name,
                                'expected_amount': expected_amount,
                                'actual_amount': txn.amount,
                                'month': txn.month.strftime('%b %Y') if txn.month else 'Unknown'
                            }
                        )
                        self.findings.append(finding)
    
    def check_double_discount(self):
        """
        Rule D: Employee Unit vs Concession Conflict
        IF employee_unit == TRUE AND concession_present == TRUE
        FLAG: DOUBLE_DISCOUNT_RISK
        """
        for unit in self.units:
            if unit.is_employee_unit:
                unit_txns = self.transactions_by_unit[unit.unit_id]
                conc_txns = [t for t in unit_txns if t.category == 'concession']
                
                if conc_txns:
                    total_concession = sum(abs(t.amount) for t in conc_txns)
                    
                    finding = AuditFinding(
                        finding_id=generate_id("finding"),
                        unit_id=unit.unit_id,
                        unit_number=unit.unit_number,
                        rule_id="DOUBLE_DISCOUNT",
                        rule_name="Double Discount Risk",
                        severity=settings.SEVERITY_CRITICAL,
                        month=None,
                        delta=-total_concession,
                        evidence={
                            'is_employee_unit': True,
                            'resident_name': unit.resident_name,
                            'total_concessions': total_concession,
                            'concession_count': len(conc_txns)
                        }
                    )
                    self.findings.append(finding)
    
    def _map_fee_to_template(self, subcategory: str) -> Optional[str]:
        """Map fee subcategory to template fee name"""
        mapping = {
            'billing_fee': 'Billing Fee',
            'cable': 'Cable',
            'cam': 'CAM',
            'hoa': 'HOA',
            'trash': 'Trash',
            'valet_trash': 'Valet Trash',
            'package_locker': 'Package Locker',
            'pest_control': 'Pest Control',
        }
        return mapping.get(subcategory)
