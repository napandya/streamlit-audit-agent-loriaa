"""
Export functionality for audit data
"""
import streamlit as st
import pandas as pd
from typing import List
from datetime import datetime
import io

from models.unit import Unit, RecurringTransaction, AuditFinding
from utils.helpers import format_currency
from storage.audit_log import AuditLog


def render_export_panel(
    units: List[Unit],
    transactions: List[RecurringTransaction],
    findings: List[AuditFinding],
    audit_log: AuditLog
):
    """
    Render export panel with download options
    """
    st.header("📤 Export Data")
    
    st.write("Download audit data and findings in various formats.")
    
    # Export format selector
    export_format = st.radio(
        "Select export format:",
        options=["Excel (recommended)", "CSV"],
        help="Choose the format for exporting data"
    )
    
    # Export options
    st.subheader("Select data to export:")
    
    col1, col2 = st.columns(2)
    
    with col1:
        export_findings = st.checkbox("Audit Findings", value=True)
        export_units = st.checkbox("Unit Summary", value=True)
    
    with col2:
        export_transactions = st.checkbox("All Transactions", value=False)
        export_summary = st.checkbox("Executive Summary", value=True)
    
    # User name for audit trail
    exporter_name = st.text_input(
        "Your name (for audit trail):",
        placeholder="Enter your name"
    )
    
    # Export button
    if st.button("📥 Generate Export", type="primary", use_container_width=True):
        if not exporter_name:
            st.error("Please enter your name for the audit trail.")
        else:
            with st.spinner("Generating export..."):
                if export_format == "Excel (recommended)":
                    export_data = generate_excel_export(
                        units, transactions, findings,
                        export_findings, export_units, export_transactions, export_summary
                    )
                    
                    filename = f"audit_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
                    mime_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    
                else:  # CSV
                    export_data = generate_csv_export(findings)
                    filename = f"audit_findings_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
                    mime_type = "text/csv"
                
                # Log export action
                audit_log.log_export(
                    export_type=export_format,
                    user=exporter_name,
                    record_count=len(findings)
                )
                
                # Download button
                st.download_button(
                    label=f"💾 Download {filename}",
                    data=export_data,
                    file_name=filename,
                    mime=mime_type,
                    use_container_width=True
                )
                
                st.success("✅ Export generated successfully!")


def generate_excel_export(
    units: List[Unit],
    transactions: List[RecurringTransaction],
    findings: List[AuditFinding],
    include_findings: bool,
    include_units: bool,
    include_transactions: bool,
    include_summary: bool
) -> bytes:
    """Generate Excel file with multiple sheets"""
    
    output = io.BytesIO()
    
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        
        # Executive Summary Sheet
        if include_summary:
            summary_data = generate_summary_data(units, transactions, findings)
            summary_df = pd.DataFrame(summary_data)
            summary_df.to_excel(writer, sheet_name='Executive Summary', index=False)
        
        # Findings Sheet
        if include_findings and findings:
            findings_df = generate_findings_dataframe(findings)
            findings_df.to_excel(writer, sheet_name='Audit Findings', index=False)
        
        # Units Sheet
        if include_units and units:
            units_df = generate_units_dataframe(units, transactions, findings)
            units_df.to_excel(writer, sheet_name='Unit Summary', index=False)
        
        # Transactions Sheet
        if include_transactions and transactions:
            transactions_df = generate_transactions_dataframe(transactions)
            transactions_df.to_excel(writer, sheet_name='All Transactions', index=False)
    
    output.seek(0)
    return output.getvalue()


def generate_csv_export(findings: List[AuditFinding]) -> bytes:
    """Generate CSV file with findings"""
    df = generate_findings_dataframe(findings)
    
    output = io.StringIO()
    df.to_csv(output, index=False)
    output.seek(0)
    
    return output.getvalue().encode('utf-8')


def generate_summary_data(
    units: List[Unit],
    transactions: List[RecurringTransaction],
    findings: List[AuditFinding]
) -> List[dict]:
    """Generate executive summary data"""
    
    total_revenue = sum(t.amount for t in transactions if t.category in ['rent', 'fee'])
    total_concessions = sum(abs(t.amount) for t in transactions if t.category == 'concession')
    net_revenue = total_revenue - total_concessions
    
    summary = [
        {'Metric': 'Total Units', 'Value': len(units)},
        {'Metric': 'Total Revenue', 'Value': format_currency(total_revenue)},
        {'Metric': 'Total Concessions', 'Value': format_currency(total_concessions)},
        {'Metric': 'Net Revenue', 'Value': format_currency(net_revenue)},
        {'Metric': '', 'Value': ''},
        {'Metric': 'Total Findings', 'Value': len(findings)},
        {'Metric': 'Critical Findings', 'Value': len([f for f in findings if f.severity == 'Critical'])},
        {'Metric': 'High Findings', 'Value': len([f for f in findings if f.severity == 'High'])},
        {'Metric': 'Medium Findings', 'Value': len([f for f in findings if f.severity == 'Medium'])},
        {'Metric': 'Low Findings', 'Value': len([f for f in findings if f.severity == 'Low'])},
        {'Metric': '', 'Value': ''},
        {'Metric': 'Open Findings', 'Value': len([f for f in findings if f.status == 'Open'])},
        {'Metric': 'Reviewed Findings', 'Value': len([f for f in findings if f.status == 'Reviewed'])},
        {'Metric': 'Overridden Findings', 'Value': len([f for f in findings if f.status == 'Overridden'])},
        {'Metric': 'Closed Findings', 'Value': len([f for f in findings if f.status == 'Closed'])},
    ]
    
    return summary


def generate_findings_dataframe(findings: List[AuditFinding]) -> pd.DataFrame:
    """Generate findings dataframe for export"""
    
    from engine.explainability import ExplainabilityEngine
    
    data = []
    for finding in findings:
        explanation = ExplainabilityEngine.explain(finding)
        
        data.append({
            'Finding ID': finding.finding_id,
            'Unit Number': finding.unit_number,
            'Rule': finding.rule_name,
            'Severity': finding.severity,
            'Month': finding.month.strftime('%b %Y') if finding.month else 'N/A',
            'Delta': finding.delta if finding.delta else 0,
            'Explanation': explanation,
            'Status': finding.status,
            'Notes': finding.notes,
            'Reviewed By': finding.reviewed_by or '',
            'Reviewed At': finding.reviewed_at.strftime('%Y-%m-%d') if finding.reviewed_at else '',
        })
    
    return pd.DataFrame(data)


def generate_units_dataframe(
    units: List[Unit],
    transactions: List[RecurringTransaction],
    findings: List[AuditFinding]
) -> pd.DataFrame:
    """Generate units summary dataframe"""
    
    from collections import defaultdict
    
    # Aggregate by unit
    unit_totals = defaultdict(lambda: {'rent': 0, 'concessions': 0, 'fees': 0})
    
    for txn in transactions:
        if txn.category == 'rent':
            unit_totals[txn.unit_id]['rent'] += txn.amount
        elif txn.category == 'concession':
            unit_totals[txn.unit_id]['concessions'] += abs(txn.amount)
        elif txn.category == 'fee':
            unit_totals[txn.unit_id]['fees'] += txn.amount
    
    # Count findings per unit
    unit_findings = defaultdict(int)
    for finding in findings:
        unit_findings[finding.unit_id] += 1
    
    data = []
    for unit in units:
        totals = unit_totals[unit.unit_id]
        
        data.append({
            'Unit Number': unit.unit_number,
            'Resident Name': unit.resident_name or 'Vacant',
            'Employee Unit': 'Yes' if unit.is_employee_unit else 'No',
            'Base Rent': unit.base_rent or 0,
            'Total Rent': totals['rent'],
            'Total Concessions': totals['concessions'],
            'Total Fees': totals['fees'],
            'Net Revenue': totals['rent'] + totals['fees'] - totals['concessions'],
            'Findings Count': unit_findings[unit.unit_id],
            'Lease Start': unit.lease_start.strftime('%Y-%m-%d') if unit.lease_start else '',
            'Lease End': unit.lease_end.strftime('%Y-%m-%d') if unit.lease_end else '',
        })
    
    return pd.DataFrame(data)


def generate_transactions_dataframe(transactions: List[RecurringTransaction]) -> pd.DataFrame:
    """Generate transactions dataframe"""
    
    data = []
    for txn in transactions:
        data.append({
            'Transaction ID': txn.transaction_id,
            'Unit Number': txn.unit_number,
            'Month': txn.month.strftime('%b %Y') if txn.month else 'N/A',
            'Category': txn.category.title(),
            'Subcategory': txn.subcategory or '',
            'Description': txn.description,
            'Amount': txn.amount,
            'Source': txn.source,
        })
    
    return pd.DataFrame(data)
