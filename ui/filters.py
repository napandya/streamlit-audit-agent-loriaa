"""
Sidebar filters and data source selector
"""
import streamlit as st
from datetime import date, datetime
from dateutil.relativedelta import relativedelta

from config import settings


def render_sidebar():
    """
    Render sidebar with filters and data source selector
    Returns: dict with selected options
    """
    st.sidebar.title(f"{settings.APP_ICON} {settings.APP_TITLE}")
    st.sidebar.markdown("---")
    
    # Data Source Selector
    st.sidebar.subheader("📂 Data Source")
    data_source = st.sidebar.radio(
        "Choose data source:",
        options=["Upload Files", "ResMan API Sync"],
        help="Select whether to upload files manually or sync from ResMan API"
    )
    
    # Property Selector
    st.sidebar.subheader("🏢 Property")
    property_name = st.sidebar.text_input(
        "Property Name",
        value=settings.DEFAULT_PROPERTY,
        help="Enter the property name"
    )
    
    # Date Range Selector
    st.sidebar.subheader("📅 Date Range")
    
    # Default to last 12 months
    default_end = date.today()
    default_start = default_end - relativedelta(months=11)
    
    col1, col2 = st.sidebar.columns(2)
    
    with col1:
        start_date = st.date_input(
            "Start Month",
            value=default_start,
            help="Select the start month for analysis"
        )
    
    with col2:
        end_date = st.date_input(
            "End Month",
            value=default_end,
            help="Select the end month for analysis"
        )
    
    # Convert to first day of month
    if start_date:
        start_date = date(start_date.year, start_date.month, 1)
    if end_date:
        end_date = date(end_date.year, end_date.month, 1)
    
    st.sidebar.markdown("---")
    
    # File Upload Section (if Upload Files is selected)
    uploaded_files = []
    if data_source == "Upload Files":
        st.sidebar.subheader("📤 Upload Files")
        uploaded_files = st.sidebar.file_uploader(
            "Upload PDF, Excel, or Word files",
            type=['pdf', 'xlsx', 'xls', 'csv', 'docx'],
            accept_multiple_files=True,
            help=f"Supported formats: PDF, Excel (.xlsx, .xls), CSV, Word (.docx). Max size: {settings.MAX_UPLOAD_SIZE_MB}MB"
        )
    
    # ResMan API Config (if ResMan Sync is selected)
    resman_config = {}
    if data_source == "ResMan API Sync":
        st.sidebar.subheader("🔧 ResMan API Config")
        
        with st.sidebar.expander("API Configuration", expanded=False):
            resman_config['api_url'] = st.text_input(
                "API URL",
                value=settings.RESMAN_API_URL,
                help="ResMan API base URL"
            )
            resman_config['api_key'] = st.text_input(
                "API Key",
                value=settings.RESMAN_API_KEY,
                type="password",
                help="Your ResMan API key"
            )
            resman_config['property_id'] = st.text_input(
                "Property ID",
                value=settings.RESMAN_PROPERTY_ID,
                help="ResMan property identifier"
            )
    
    # Additional Filters
    st.sidebar.markdown("---")
    st.sidebar.subheader("🔍 Filters")
    
    # Severity filter
    severity_filter = st.sidebar.multiselect(
        "Filter by Severity",
        options=['Critical', 'High', 'Medium', 'Low'],
        default=['Critical', 'High', 'Medium', 'Low'],
        help="Filter findings by severity level"
    )
    
    # Status filter
    status_filter = st.sidebar.multiselect(
        "Filter by Status",
        options=['Open', 'Reviewed', 'Overridden', 'Closed'],
        default=['Open'],
        help="Filter findings by status"
    )
    
    return {
        'data_source': data_source,
        'property_name': property_name,
        'start_date': start_date,
        'end_date': end_date,
        'uploaded_files': uploaded_files,
        'resman_config': resman_config,
        'severity_filter': severity_filter,
        'status_filter': status_filter
    }
