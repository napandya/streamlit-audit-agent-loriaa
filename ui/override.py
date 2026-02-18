"""
Override panel for audit findings
"""
import streamlit as st
from typing import List
from datetime import datetime

from models.unit import AuditFinding
from storage.audit_log import AuditLog


def render_override_panel(findings: List[AuditFinding], audit_log: AuditLog):
    """
    Render override panel with audit trail
    """
    st.header("📋 Override Panel")
    
    if not findings:
        st.info("No findings to override.")
        return
    
    st.write("Update the status of audit findings and provide notes for the audit trail.")
    
    # Filter to open or reviewed findings
    actionable_findings = [f for f in findings if f.status in ['Open', 'Reviewed']]
    
    if not actionable_findings:
        st.success("✅ All findings have been reviewed or overridden.")
        return
    
    # Create a selection list
    finding_options = {}
    for finding in actionable_findings:
        label = f"Unit {finding.unit_number} - {finding.rule_name} ({finding.severity})"
        finding_options[label] = finding
    
    st.subheader("Select Finding to Override")
    
    selected_label = st.selectbox(
        "Choose a finding:",
        options=list(finding_options.keys()),
        help="Select a finding to update its status"
    )
    
    if selected_label:
        finding = finding_options[selected_label]
        
        st.markdown("---")
        
        # Display finding details
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.write(f"**Unit:** {finding.unit_number}")
            st.write(f"**Rule:** {finding.rule_name}")
        
        with col2:
            st.write(f"**Severity:** {finding.severity}")
            st.write(f"**Current Status:** {finding.status}")
        
        with col3:
            if finding.month:
                st.write(f"**Month:** {finding.month.strftime('%b %Y')}")
        
        st.markdown("---")
        
        # Override form
        with st.form(key=f"override_form_{finding.finding_id}"):
            st.subheader("Update Finding")
            
            # Status selector
            new_status = st.selectbox(
                "New Status:",
                options=['Open', 'Reviewed', 'Overridden', 'Closed'],
                index=['Open', 'Reviewed', 'Overridden', 'Closed'].index(finding.status),
                help="Update the status of this finding"
            )
            
            # Notes
            notes = st.text_area(
                "Notes:",
                value=finding.notes,
                help="Provide explanation for the status change",
                placeholder="Enter notes about this finding..."
            )
            
            # Reviewer name
            reviewer = st.text_input(
                "Your Name:",
                help="Enter your name for the audit trail"
            )
            
            # Submit button
            col1, col2 = st.columns([1, 3])
            with col1:
                submit = st.form_submit_button("💾 Save", use_container_width=True)
            with col2:
                if finding.status != 'Open':
                    revert = st.form_submit_button("↩️ Revert to Open", use_container_width=True)
                else:
                    revert = False
            
            if submit:
                if not reviewer:
                    st.error("Please enter your name for the audit trail.")
                else:
                    # Update finding
                    finding.status = new_status
                    finding.notes = notes
                    finding.reviewed_by = reviewer
                    finding.reviewed_at = datetime.now().date()
                    
                    # Log the action
                    audit_log.log_finding_override(
                        finding_id=finding.finding_id,
                        unit_number=finding.unit_number,
                        rule_name=finding.rule_name,
                        user=reviewer,
                        status=new_status,
                        notes=notes
                    )
                    
                    st.success(f"✅ Finding updated successfully! Status: {new_status}")
                    st.balloons()
            
            if revert:
                # Revert to Open
                finding.status = 'Open'
                finding.notes = notes
                finding.reviewed_by = reviewer
                finding.reviewed_at = datetime.now().date()
                
                # Log the action
                audit_log.log_finding_override(
                    finding_id=finding.finding_id,
                    unit_number=finding.unit_number,
                    rule_name=finding.rule_name,
                    user=reviewer,
                    status='Open',
                    notes="Reverted to Open"
                )
                
                st.success("✅ Finding reverted to Open status!")


def render_audit_trail(audit_log: AuditLog):
    """Render recent audit trail"""
    st.subheader("📜 Recent Audit Trail")
    
    logs = audit_log.get_recent_logs(limit=20)
    
    if not logs:
        st.info("No audit trail entries yet.")
        return
    
    # Display logs
    for log in reversed(logs):  # Most recent first
        timestamp = log.get('timestamp', '')
        action = log.get('action', '')
        user = log.get('user', '')
        details = log.get('details', {})
        
        # Format timestamp
        try:
            dt = datetime.fromisoformat(timestamp)
            timestamp_str = dt.strftime('%Y-%m-%d %H:%M:%S')
        except:
            timestamp_str = timestamp
        
        # Create expander for each log entry
        if action == 'finding_override':
            title = f"{timestamp_str} - {user} updated {details.get('unit_number', 'Unknown')} - {details.get('rule_name', 'Unknown')}"
        elif action == 'data_load':
            title = f"{timestamp_str} - {user} loaded {details.get('source', 'data')}"
        elif action == 'export':
            title = f"{timestamp_str} - {user} exported {details.get('export_type', 'data')}"
        else:
            title = f"{timestamp_str} - {action}"
        
        with st.expander(title):
            st.write(f"**Action:** {action}")
            st.write(f"**User:** {user}")
            st.write(f"**Timestamp:** {timestamp_str}")
            st.write(f"**Details:**")
            for key, value in details.items():
                st.write(f"  • {key}: {value}")
