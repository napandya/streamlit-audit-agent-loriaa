"""
KPI Overview Dashboard
"""
import streamlit as st
from typing import List, Dict
import pandas as pd

from models.unit import AuditFinding, RecurringTransaction
from utils.helpers import format_currency, format_percentage


def render_kpi_overview(
    transactions: List[RecurringTransaction],
    findings: List[AuditFinding],
    monthly_aggregates: Dict
):
    """
    Render KPI overview with key metrics cards
    """
    st.header("📊 KPI Overview")
    
    # Calculate KPIs
    total_revenue = sum(t.amount for t in transactions if t.category in ['rent', 'fee'])
    total_concessions = sum(abs(t.amount) for t in transactions if t.category == 'concession')
    total_credits = sum(abs(t.amount) for t in transactions if t.category == 'credit')
    net_revenue = total_revenue - total_concessions - total_credits
    
    concession_pct = (total_concessions / total_revenue * 100) if total_revenue > 0 else 0
    
    # Count findings by severity
    critical_count = len([f for f in findings if f.severity == 'Critical'])
    high_count = len([f for f in findings if f.severity == 'High'])
    medium_count = len([f for f in findings if f.severity == 'Medium'])
    low_count = len([f for f in findings if f.severity == 'Low'])
    total_findings = len(findings)
    
    # Calculate lease cliff risk score
    lease_cliff_findings = [f for f in findings if f.rule_id == 'LEASE_CLIFF']
    lease_cliff_score = min(len(lease_cliff_findings) * 10, 100)  # 0-100 scale
    
    # Display metrics in columns
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric(
            label="💰 Total Revenue",
            value=format_currency(total_revenue),
            delta=None,
            help="Total rent and recurring fees for the selected period"
        )
        st.metric(
            label="💸 Concessions",
            value=format_currency(total_concessions),
            delta=f"{concession_pct:.1f}% of revenue",
            delta_color="inverse",
            help="Total concessions and discounts applied"
        )
    
    with col2:
        st.metric(
            label="📉 Net Revenue",
            value=format_currency(net_revenue),
            delta=None,
            help="Revenue after concessions and credits"
        )
        st.metric(
            label="🔄 Credits",
            value=format_currency(total_credits),
            delta=None,
            help="Total credits and adjustments"
        )
    
    with col3:
        st.metric(
            label="⚠️ Total Findings",
            value=total_findings,
            delta=None,
            help="Total number of audit findings"
        )
        
        # Findings breakdown
        findings_breakdown = f"🔴 {critical_count} | 🟠 {high_count} | 🟡 {medium_count} | 🟢 {low_count}"
        st.caption(findings_breakdown)
        st.caption("Critical | High | Medium | Low")
    
    with col4:
        # Lease cliff risk indicator
        risk_color = "🔴" if lease_cliff_score >= 50 else "🟡" if lease_cliff_score >= 25 else "🟢"
        st.metric(
            label=f"{risk_color} Lease Cliff Risk",
            value=f"{lease_cliff_score}/100",
            delta=f"{len(lease_cliff_findings)} cliffs detected",
            delta_color="inverse",
            help="Risk score based on detected revenue cliffs"
        )
    
    # Revenue breakdown
    st.markdown("---")
    st.subheader("📊 Revenue Structure")
    
    col1, col2 = st.columns(2)
    
    with col1:
        # Revenue pie chart
        revenue_breakdown = {
            'Base Rent': sum(t.amount for t in transactions if t.category == 'rent'),
            'Recurring Fees': sum(t.amount for t in transactions if t.category == 'fee'),
            'Concessions': -sum(abs(t.amount) for t in transactions if t.category == 'concession'),
            'Credits': -sum(abs(t.amount) for t in transactions if t.category == 'credit'),
        }
        
        df_revenue = pd.DataFrame([
            {'Category': k, 'Amount': v} 
            for k, v in revenue_breakdown.items() if v != 0
        ])
        
        if not df_revenue.empty:
            st.dataframe(
                df_revenue.style.format({'Amount': format_currency}),
                hide_index=True,
                use_container_width=True
            )
    
    with col2:
        # Key metrics summary
        avg_rent = revenue_breakdown['Base Rent'] / len(set(t.unit_id for t in transactions if t.category == 'rent')) if any(t.category == 'rent' for t in transactions) else 0
        
        st.metric("📍 Average Rent per Unit", format_currency(avg_rent))
        st.metric("📉 Concession Rate", f"{concession_pct:.1f}%")
        
        # Calculate occupied units
        unique_units = len(set(t.unit_id for t in transactions))
        st.metric("🏠 Units with Charges", unique_units)


def render_summary_stats(findings_stats: Dict):
    """Render summary statistics"""
    st.markdown("---")
    st.subheader("📈 Audit Summary")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.write("**Findings by Rule:**")
        for rule, count in findings_stats.get('by_rule', {}).items():
            st.write(f"• {rule}: {count}")
    
    with col2:
        st.write("**Affected Units:**")
        st.write(f"Total units with findings: {findings_stats.get('affected_units', 0)}")
