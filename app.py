"""
Village Green Property Recurring Transaction & Concession Audit System
Main Streamlit Application
"""
import streamlit as st
import tempfile
import os
from pathlib import Path
from datetime import datetime

# Import models and engines
from models.canonical_model import CanonicalModel
from engine.date_range_engine import DateRangeEngine
from engine.anomaly_detector import AnomalyDetector
from engine.explainability import ExplainabilityEngine

# Import ingestion
from ingestion.loader import FileLoader
from ingestion.resman_client import ResManClient

# Import storage
from storage.database import Database
from storage.audit_log import AuditLog

# Import UI components
from ui.filters import render_sidebar
from ui.dashboard import render_kpi_overview, render_summary_stats
from ui.charts import render_revenue_trend, render_concession_analysis, render_lease_cliff_heatmap
from ui.unit_view import render_unit_drilldown
from ui.findings import render_findings_table, render_findings_summary
from ui.override import render_override_panel, render_audit_trail
from ui.export import render_export_panel

# Import config
from config import settings


# Page configuration
st.set_page_config(
    page_title=settings.APP_TITLE,
    page_icon=settings.APP_ICON,
    layout="wide",
    initial_sidebar_state="expanded"
)


def initialize_session_state():
    """Initialize session state variables"""
    if 'canonical_model' not in st.session_state:
        st.session_state.canonical_model = CanonicalModel()
    
    if 'data_loaded' not in st.session_state:
        st.session_state.data_loaded = False
    
    if 'audit_log' not in st.session_state:
        st.session_state.audit_log = AuditLog()
    
    if 'database' not in st.session_state:
        st.session_state.database = Database()


def load_data_from_files(uploaded_files, canonical_model, audit_log):
    """Load data from uploaded files"""
    loader = FileLoader()
    
    success_count = 0
    error_messages = []
    
    # Create temporary directory for uploaded files
    with tempfile.TemporaryDirectory() as temp_dir:
        for uploaded_file in uploaded_files:
            # Save uploaded file to temp directory
            temp_path = os.path.join(temp_dir, uploaded_file.name)
            with open(temp_path, 'wb') as f:
                f.write(uploaded_file.getbuffer())
            
            # Load the file
            success, message = loader.load_file(temp_path, canonical_model)
            
            if success:
                success_count += 1
            else:
                error_messages.append(f"{uploaded_file.name}: {message}")
    
    # Log the data load
    if success_count > 0:
        audit_log.log_data_load(
            source='file_upload',
            file_name=f"{success_count} files",
            user='System',
            records_loaded=len(canonical_model.transactions)
        )
    
    return success_count, error_messages


def load_data_from_resman(resman_config, start_date, end_date, canonical_model, audit_log):
    """Load data from ResMan API"""
    client = ResManClient(
        api_url=resman_config.get('api_url'),
        api_key=resman_config.get('api_key'),
        property_id=resman_config.get('property_id')
    )
    
    # Authenticate
    if not client.authenticate():
        return False, "Failed to authenticate with ResMan API. Using stub mode."
    
    # Fetch data
    success = client.fetch_recurring_transactions(start_date, end_date, canonical_model)
    
    if success:
        # Log the data load
        audit_log.log_data_load(
            source='resman_api',
            file_name=f"Property {resman_config.get('property_id')}",
            user='System',
            records_loaded=len(canonical_model.transactions)
        )
    
    return success, "Data loaded successfully from ResMan API (stub mode)"


def main():
    """Main application function"""
    
    # Initialize session state
    initialize_session_state()
    
    # Render sidebar and get filters
    filters = render_sidebar()
    
    # Main content area
    st.title(f"{settings.APP_ICON} {settings.APP_TITLE}")
    st.markdown("---")
    
    # Data loading section
    canonical_model = st.session_state.canonical_model
    audit_log = st.session_state.audit_log
    
    # Load data based on selected source
    if filters['data_source'] == 'Upload Files':
        if filters['uploaded_files']:
            if not st.session_state.data_loaded:
                with st.spinner("Loading and parsing files..."):
                    success_count, errors = load_data_from_files(
                        filters['uploaded_files'],
                        canonical_model,
                        audit_log
                    )
                    
                    if success_count > 0:
                        st.success(f"✅ Successfully loaded {success_count} file(s)")
                        st.session_state.data_loaded = True
                    
                    if errors:
                        st.error("Errors loading some files:")
                        for error in errors:
                            st.error(f"• {error}")
        else:
            st.info("👆 Please upload files using the sidebar to begin analysis.")
            return
    
    elif filters['data_source'] == 'ResMan API Sync':
        if st.sidebar.button("🔄 Sync from ResMan", type="primary"):
            with st.spinner("Syncing data from ResMan API..."):
                canonical_model.clear()  # Clear existing data
                success, message = load_data_from_resman(
                    filters['resman_config'],
                    filters['start_date'],
                    filters['end_date'],
                    canonical_model,
                    audit_log
                )
                
                if success:
                    st.success(message)
                    st.session_state.data_loaded = True
                else:
                    st.warning(message)
                    st.session_state.data_loaded = True  # Allow stub mode
    
    # If no data loaded, show instructions
    if not st.session_state.data_loaded:
        st.info("No data loaded yet. Please select a data source and load data to begin analysis.")
        return
    
    # Get data from canonical model
    units = canonical_model.units
    transactions = canonical_model.transactions
    
    if not transactions:
        st.warning("No transaction data found. Please check your data source.")
        return
    
    # Filter transactions by date range
    date_engine = DateRangeEngine(transactions)
    filtered_transactions = date_engine.filter_by_date_range(
        filters['start_date'],
        filters['end_date']
    )
    
    # Run anomaly detection
    with st.spinner("Running audit rules..."):
        detector = AnomalyDetector(units, filtered_transactions)
        findings = detector.detect()
        
        # Add explanations to findings
        for finding in findings:
            finding.explanation = ExplainabilityEngine.explain(finding)
    
    # Calculate aggregates
    monthly_aggregates = date_engine.aggregate_by_month(
        filters['start_date'],
        filters['end_date']
    )
    
    unit_aggregates = date_engine.aggregate_by_unit(
        filters['start_date'],
        filters['end_date']
    )
    
    revenue_trend = date_engine.calculate_revenue_trend(
        filters['start_date'],
        filters['end_date']
    )
    
    # Save to database if enabled
    if settings.USE_DATABASE:
        db = st.session_state.database
        db.save_units(units)
        db.save_transactions(filtered_transactions)
        db.save_findings(findings)
    
    # Create tabs for different views
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "📊 KPI Overview",
        "📉 Revenue Trend",
        "🔍 Unit Drilldown",
        "⚠️ Audit Findings",
        "📋 Override Panel",
        "📤 Export"
    ])
    
    # Tab 1: KPI Overview
    with tab1:
        render_kpi_overview(filtered_transactions, findings, monthly_aggregates)
        
        # Summary stats
        findings_stats = detector.get_summary_stats()
        render_summary_stats(findings_stats)
    
    # Tab 2: Revenue Trend
    with tab2:
        render_revenue_trend(revenue_trend)
        
        col1, col2 = st.columns(2)
        
        with col1:
            render_concession_analysis(filtered_transactions)
        
        with col2:
            render_lease_cliff_heatmap(findings)
    
    # Tab 3: Unit Drilldown
    with tab3:
        render_unit_drilldown(units, filtered_transactions, findings, unit_aggregates)
    
    # Tab 4: Audit Findings
    with tab4:
        render_findings_table(
            findings,
            filters['severity_filter'],
            filters['status_filter']
        )
        
        st.markdown("---")
        render_findings_summary(findings)
    
    # Tab 5: Override Panel
    with tab5:
        render_override_panel(findings, audit_log)
        
        st.markdown("---")
        render_audit_trail(audit_log)
    
    # Tab 6: Export
    with tab6:
        render_export_panel(units, filtered_transactions, findings, audit_log)
    
    # Footer
    st.markdown("---")
    st.caption(f"Village Green Property Audit System | Data as of {datetime.now().strftime('%Y-%m-%d %H:%M')}")


if __name__ == "__main__":
    main()
