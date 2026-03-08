"""
Full Report tab renderer — styled, professional audit report layout.
"""
import streamlit as st
from datetime import datetime
from typing import Optional

from agents.audit_agent import AuditResult


# ---------------------------------------------------------------------------
# Styling
# ---------------------------------------------------------------------------

_REPORT_CSS = """
<style>
.audit-report-header {
    background: linear-gradient(135deg, #1e3a5f 0%, #2d5f8a 100%);
    color: white;
    padding: 24px 32px;
    border-radius: 12px;
    margin-bottom: 24px;
}
.audit-report-header h1 {
    color: white !important;
    margin-bottom: 4px;
    font-size: 1.8rem;
}
.audit-report-header p {
    color: #ccdae8;
    margin: 0;
    font-size: 0.95rem;
}
.severity-pill {
    display: inline-block;
    padding: 4px 14px;
    border-radius: 20px;
    font-weight: 600;
    font-size: 0.85rem;
    margin-right: 6px;
    color: white;
}
.pill-critical { background: #d32f2f; }
.pill-high     { background: #f57c00; }
.pill-medium   { background: #fbc02d; color: #333; }
.pill-low      { background: #66bb6a; }
.report-body {
    background: #fafbfc;
    border: 1px solid #e0e4e8;
    border-radius: 10px;
    padding: 28px 32px;
    font-size: 0.97rem;
    line-height: 1.7;
    margin-bottom: 20px;
}
.report-body h1, .report-body h2, .report-body h3 {
    color: #1e3a5f;
    border-bottom: 1px solid #e0e4e8;
    padding-bottom: 6px;
    margin-top: 24px;
}
.report-body ul { padding-left: 20px; }
.report-body li { margin-bottom: 4px; }
</style>
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _severity_pills(counts: dict) -> str:
    """Render severity counts as coloured pills."""
    parts = []
    for sev, cls in [("critical", "pill-critical"), ("high", "pill-high"),
                     ("medium", "pill-medium"), ("low", "pill-low")]:
        n = counts.get(sev, 0)
        if n:
            parts.append(f'<span class="severity-pill {cls}">{sev.upper()}: {n}</span>')
    return " ".join(parts) if parts else '<span style="color:#66bb6a">No findings</span>'


def _summary_metrics(audit_result: AuditResult) -> None:
    """Show top-level severity metrics as Streamlit metric cards."""
    counts = audit_result.severity_counts
    total = sum(counts.values())
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Total Findings", total)
    c2.metric("🔴 Critical", counts.get("critical", 0))
    c3.metric("🟠 High", counts.get("high", 0))
    c4.metric("🟡 Medium", counts.get("medium", 0))
    c5.metric("🟢 Low", counts.get("low", 0))


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def render_report_tab(audit_result: Optional[AuditResult], audit_timestamp: Optional[datetime] = None) -> None:
    """Render the Full Report tab."""

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

    # Inject CSS
    st.markdown(_REPORT_CSS, unsafe_allow_html=True)

    # Header banner
    ts_str = audit_timestamp.strftime("%B %d, %Y at %I:%M %p") if audit_timestamp else "N/A"
    pills_html = _severity_pills(audit_result.severity_counts)
    st.markdown(
        f'<div class="audit-report-header">'
        f'<h1>📄 Property Audit Report</h1>'
        f'<p>Generated: {ts_str} &nbsp;|&nbsp; Findings: {pills_html}</p>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # KPI metrics row
    _summary_metrics(audit_result)
    st.markdown("")

    # Report body in styled container
    report_text = audit_result.report or "_No report content was generated._"
    st.markdown(
        f'<div class="report-body">{_md_to_html(report_text)}</div>',
        unsafe_allow_html=True,
    )

    st.markdown("---")

    # Downloads
    dl1, dl2 = st.columns(2)
    with dl1:
        st.download_button(
            "⬇️ Download Report (Markdown)",
            data=report_text,
            file_name="audit_report.md",
            mime="text/markdown",
        )
    with dl2:
        # Also offer a plain-text version
        st.download_button(
            "⬇️ Download Report (Text)",
            data=report_text,
            file_name="audit_report.txt",
            mime="text/plain",
        )


def _md_to_html(md_text: str) -> str:
    """Best-effort markdown → HTML. Falls back to <pre> if markdown lib absent."""
    try:
        import markdown
        return markdown.markdown(md_text, extensions=["tables", "fenced_code", "nl2br"])
    except ImportError:
        # Minimal fallback: convert markdown headings and lists
        import html as _html
        escaped = _html.escape(md_text)
        # Turn markdown headings into HTML
        lines = escaped.split("\n")
        out: list[str] = []
        for line in lines:
            stripped = line.lstrip()
            if stripped.startswith("### "):
                out.append(f"<h3>{stripped[4:]}</h3>")
            elif stripped.startswith("## "):
                out.append(f"<h2>{stripped[3:]}</h2>")
            elif stripped.startswith("# "):
                out.append(f"<h1>{stripped[2:]}</h1>")
            elif stripped.startswith(("- ", "* ", "• ")):
                out.append(f"<li>{stripped[2:]}</li>")
            elif stripped == "":
                out.append("<br/>")
            else:
                out.append(f"<p>{line}</p>")
        return "\n".join(out)
