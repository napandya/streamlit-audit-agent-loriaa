"""
Full Report tab renderer.
"""
import streamlit as st
from datetime import datetime
from typing import Optional

from agents.audit_agent import AuditResult


def render_report_tab(audit_result: Optional[AuditResult], audit_timestamp: Optional[datetime] = None) -> None:
    """Render the Full Report tab."""
    st.subheader("📄 Full Audit Report")

    if audit_result is None:
        st.warning(
            "🤖 **No AI audit report available yet.**\n\n"
            "This tab will display a full narrative audit report once you run the AI audit. "
            "Click **🚀 Run AI Audit** in the sidebar to generate it.\n\n"
            "The Concession Check tab (auto-populated) shows rule-based flags — "
            "this report adds AI-driven analysis on top of that.",
            icon="⏳",
        )
        return

    if audit_timestamp:
        st.caption(f"Audit run at: {audit_timestamp.strftime('%Y-%m-%d %H:%M:%S')}")

    st.markdown(audit_result.report)

    st.markdown("---")

    # Download as markdown
    st.download_button(
        "⬇️ Download Report (Markdown)",
        data=audit_result.report,
        file_name="audit_report.md",
        mime="text/markdown",
    )
