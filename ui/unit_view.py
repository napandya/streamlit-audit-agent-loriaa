"""
Unit drilldown view with search and filter
"""
import streamlit as st
import pandas as pd
from typing import List, Dict

from models.unit import Unit, RecurringTransaction, AuditFinding
from utils.helpers import format_currency


def render_unit_drilldown(
    units: List[Unit],
    transactions: List[RecurringTransaction],
    findings: List[AuditFinding],
    unit_aggregates: Dict
):
    """
    Render unit drilldown table with search and filter
    """
    st.header("🔍 Unit Drilldown")
    
    if not units:
        st.info("No unit data available.")
        return
    
    # Search box
    search = st.text_input("🔎 Search units", placeholder="Enter unit number or resident name...")
    
    # Build unit summary dataframe
    unit_data = []
    
    for unit in units:
        # Get aggregated data for this unit
        agg = unit_aggregates.get(unit.unit_id, {})
        
        # Get findings for this unit
        unit_findings = [f for f in findings if f.unit_id == unit.unit_id]
        finding_count = len(unit_findings)
        
        # Highest severity
        severities = [f.severity for f in unit_findings]
        highest_severity = 'None'
        if 'Critical' in severities:
            highest_severity = 'Critical'
        elif 'High' in severities:
            highest_severity = 'High'
        elif 'Medium' in severities:
            highest_severity = 'Medium'
        elif 'Low' in severities:
            highest_severity = 'Low'
        
        unit_data.append({
            'Unit': unit.unit_number,
            'Resident': unit.resident_name or 'Vacant',
            'Employee': '✓' if unit.is_employee_unit else '',
            'Base Rent': unit.base_rent or 0,
            'Total Rent': agg.get('rent', 0),
            'Concessions': agg.get('concessions', 0),
            'Fees': agg.get('fees', 0),
            'Net Revenue': agg.get('net', 0),
            'Findings': finding_count,
            'Severity': highest_severity,
            '_unit_id': unit.unit_id  # For lookup
        })
    
    df = pd.DataFrame(unit_data)
    
    # Apply search filter
    if search:
        search_lower = search.lower()
        df = df[
            df['Unit'].astype(str).str.lower().str.contains(search_lower) |
            df['Resident'].astype(str).str.lower().str.contains(search_lower)
        ]
    
    # Sort by findings count (descending) then by unit number
    df = df.sort_values(['Findings', 'Unit'], ascending=[False, True])
    
    # Display summary metrics
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Units", len(df))
    with col2:
        units_with_findings = len(df[df['Findings'] > 0])
        st.metric("Units with Findings", units_with_findings)
    with col3:
        employee_units = len(df[df['Employee'] == '✓'])
        st.metric("Employee Units", employee_units)
    with col4:
        total_net = df['Net Revenue'].sum()
        st.metric("Total Net Revenue", format_currency(total_net))
    
    st.markdown("---")
    
    # Display table
    display_df = df.drop(columns=['_unit_id']).copy()
    
    # Format currency columns
    for col in ['Base Rent', 'Total Rent', 'Concessions', 'Fees', 'Net Revenue']:
        display_df[col] = display_df[col].apply(format_currency)
    
    # Color code severity
    def highlight_severity(row):
        severity = row['Severity']
        if severity == 'Critical':
            return ['background-color: #ffcccc'] * len(row)
        elif severity == 'High':
            return ['background-color: #ffe6cc'] * len(row)
        elif severity == 'Medium':
            return ['background-color: #ffffcc'] * len(row)
        elif severity == 'Low':
            return ['background-color: #e6f2ff'] * len(row)
        else:
            return [''] * len(row)
    
    st.dataframe(
        display_df.style.apply(highlight_severity, axis=1),
        hide_index=True,
        use_container_width=True,
        height=400
    )
    
    # Unit detail expander
    st.markdown("---")
    st.subheader("📋 Unit Details")
    
    # Unit selector
    unit_options = df['Unit'].tolist()
    if unit_options:
        selected_unit = st.selectbox(
            "Select a unit to view details:",
            options=unit_options,
            format_func=lambda x: f"Unit {x}"
        )
        
        if selected_unit:
            # Get the unit ID
            unit_id = df[df['Unit'] == selected_unit]['_unit_id'].iloc[0]
            
            # Find the unit object
            unit = next((u for u in units if u.unit_id == unit_id), None)
            
            if unit:
                render_unit_detail(unit, transactions, findings)


def render_unit_detail(
    unit: Unit,
    transactions: List[RecurringTransaction],
    findings: List[AuditFinding]
):
    """Render detailed view for a single unit"""
    
    # Unit info
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.write(f"**Unit:** {unit.unit_number}")
        st.write(f"**Resident:** {unit.resident_name or 'Vacant'}")
        if unit.is_employee_unit:
            st.warning("⚠️ Employee Unit")
    
    with col2:
        if unit.base_rent:
            st.write(f"**Base Rent:** {format_currency(unit.base_rent)}")
        if unit.lease_start:
            st.write(f"**Lease Start:** {unit.lease_start.strftime('%b %d, %Y')}")
        if unit.lease_end:
            st.write(f"**Lease End:** {unit.lease_end.strftime('%b %d, %Y')}")
    
    with col3:
        unit_txns = [t for t in transactions if t.unit_id == unit.unit_id]
        st.write(f"**Total Transactions:** {len(unit_txns)}")
        
        unit_findings = [f for f in findings if f.unit_id == unit.unit_id]
        st.write(f"**Findings:** {len(unit_findings)}")
    
    # Transactions table
    st.markdown("---")
    st.write("**Transactions:**")
    
    unit_txns = [t for t in transactions if t.unit_id == unit.unit_id]
    
    if unit_txns:
        txn_data = []
        for txn in unit_txns:
            txn_data.append({
                'Month': txn.month.strftime('%b %Y') if txn.month else 'N/A',
                'Category': txn.category.title(),
                'Description': txn.description,
                'Amount': format_currency(txn.amount),
                'Source': txn.source
            })
        
        txn_df = pd.DataFrame(txn_data)
        txn_df = txn_df.sort_values('Month')
        
        st.dataframe(
            txn_df,
            hide_index=True,
            use_container_width=True
        )
    else:
        st.info("No transactions found for this unit.")
    
    # Findings for this unit
    st.markdown("---")
    st.write("**Audit Findings:**")
    
    unit_findings = [f for f in findings if f.unit_id == unit.unit_id]
    
    if unit_findings:
        for finding in unit_findings:
            severity_emoji = {
                'Critical': '🔴',
                'High': '🟠',
                'Medium': '🟡',
                'Low': '🟢'
            }
            
            with st.expander(f"{severity_emoji.get(finding.severity, '⚪')} {finding.rule_name} - {finding.severity}"):
                st.write(f"**Month:** {finding.month.strftime('%b %Y') if finding.month else 'N/A'}")
                st.write(f"**Status:** {finding.status}")
                
                if finding.delta:
                    st.write(f"**Delta:** {format_currency(finding.delta)}")
                
                st.write(f"**Evidence:**")
                for key, value in finding.evidence.items():
                    if isinstance(value, float):
                        if 'pct' in key.lower() or 'percent' in key.lower():
                            st.write(f"  • {key}: {value * 100:.1f}%")
                        elif 'amount' in key.lower() or 'rent' in key.lower():
                            st.write(f"  • {key}: {format_currency(value)}")
                        else:
                            st.write(f"  • {key}: {value}")
                    else:
                        st.write(f"  • {key}: {value}")
                
                if finding.notes:
                    st.write(f"**Notes:** {finding.notes}")
    else:
        st.success("✅ No findings for this unit.")
