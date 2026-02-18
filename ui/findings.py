"""
Audit findings table
"""
import streamlit as st
import pandas as pd
from typing import List

from models.unit import AuditFinding
from engine.explainability import ExplainabilityEngine
from utils.helpers import format_currency


def render_findings_table(findings: List[AuditFinding], severity_filter: List[str], status_filter: List[str]):
    """
    Render audit findings table with filtering
    """
    st.header("⚠️ Audit Findings")
    
    if not findings:
        st.success("✅ No audit findings! All checks passed.")
        return
    
    # Apply filters
    filtered_findings = [
        f for f in findings
        if f.severity in severity_filter and f.status in status_filter
    ]
    
    if not filtered_findings:
        st.info(f"No findings match the selected filters (Severity: {severity_filter}, Status: {status_filter})")
        return
    
    # Display summary
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Total Findings", len(filtered_findings))
    
    with col2:
        critical = len([f for f in filtered_findings if f.severity == 'Critical'])
        st.metric("Critical", critical)
    
    with col3:
        high = len([f for f in filtered_findings if f.severity == 'High'])
        st.metric("High", high)
    
    with col4:
        open_count = len([f for f in filtered_findings if f.status == 'Open'])
        st.metric("Open", open_count)
    
    st.markdown("---")
    
    # Build findings dataframe
    findings_data = []
    
    for finding in filtered_findings:
        # Generate explanation
        explanation = ExplainabilityEngine.explain(finding)
        
        findings_data.append({
            'ID': finding.finding_id[:8],  # Short ID
            'Unit': finding.unit_number,
            'Rule': finding.rule_name,
            'Severity': finding.severity,
            'Month': finding.month.strftime('%b %Y') if finding.month else 'N/A',
            'Delta': finding.delta if finding.delta else 0,
            'Explanation': explanation,
            'Status': finding.status,
            '_finding': finding  # Store full finding for reference
        })
    
    df = pd.DataFrame(findings_data)
    
    # Sort by severity and unit
    severity_order = {'Critical': 0, 'High': 1, 'Medium': 2, 'Low': 3}
    df['_severity_order'] = df['Severity'].map(severity_order)
    df = df.sort_values(['_severity_order', 'Unit', 'Month'])
    df = df.drop(columns=['_severity_order'])
    
    # Display table with expandable rows
    for idx, row in df.iterrows():
        severity_emoji = {
            'Critical': '🔴',
            'High': '🟠',
            'Medium': '🟡',
            'Low': '🟢'
        }
        
        status_emoji = {
            'Open': '⚪',
            'Reviewed': '🔵',
            'Overridden': '🟣',
            'Closed': '✅'
        }
        
        # Create expander with severity and rule name
        title = f"{severity_emoji.get(row['Severity'], '⚪')} Unit {row['Unit']} - {row['Rule']} {status_emoji.get(row['Status'], '')}"
        
        with st.expander(title):
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.write(f"**Finding ID:** {row['ID']}")
                st.write(f"**Unit:** {row['Unit']}")
                st.write(f"**Month:** {row['Month']}")
            
            with col2:
                st.write(f"**Rule:** {row['Rule']}")
                st.write(f"**Severity:** {row['Severity']}")
                st.write(f"**Status:** {row['Status']}")
            
            with col3:
                if row['Delta'] != 0:
                    st.write(f"**Impact:** {format_currency(row['Delta'])}")
            
            st.markdown("---")
            st.write("**Explanation:**")
            st.info(row['Explanation'])
            
            # Evidence details
            finding = row['_finding']
            if finding.evidence:
                with st.expander("📋 View Evidence Details"):
                    for key, value in finding.evidence.items():
                        if isinstance(value, float):
                            if 'pct' in key.lower() or 'percent' in key.lower():
                                st.write(f"• **{key}:** {value * 100:.1f}%")
                            elif 'amount' in key.lower() or 'rent' in key.lower() or 'concession' in key.lower():
                                st.write(f"• **{key}:** {format_currency(value)}")
                            else:
                                st.write(f"• **{key}:** {value:.2f}")
                        else:
                            st.write(f"• **{key}:** {value}")
            
            # Notes
            if finding.notes:
                st.write(f"**Notes:** {finding.notes}")
            
            # Show review info if reviewed
            if finding.reviewed_by:
                st.write(f"**Reviewed by:** {finding.reviewed_by}")
                if finding.reviewed_at:
                    st.write(f"**Reviewed at:** {finding.reviewed_at.strftime('%Y-%m-%d %H:%M')}")


def render_findings_summary(findings: List[AuditFinding]):
    """Render a summary of findings by rule and severity"""
    st.subheader("📊 Findings Summary")
    
    # Group by rule
    from collections import defaultdict
    by_rule = defaultdict(lambda: {'Critical': 0, 'High': 0, 'Medium': 0, 'Low': 0, 'Total': 0})
    
    for finding in findings:
        by_rule[finding.rule_name][finding.severity] += 1
        by_rule[finding.rule_name]['Total'] += 1
    
    # Convert to dataframe
    summary_data = []
    for rule, counts in by_rule.items():
        summary_data.append({
            'Rule': rule,
            'Critical': counts['Critical'],
            'High': counts['High'],
            'Medium': counts['Medium'],
            'Low': counts['Low'],
            'Total': counts['Total']
        })
    
    df = pd.DataFrame(summary_data)
    df = df.sort_values('Total', ascending=False)
    
    st.dataframe(
        df,
        hide_index=True,
        use_container_width=True
    )
