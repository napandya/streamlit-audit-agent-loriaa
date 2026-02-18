# 🏢 Village Green Property Audit System

A comprehensive Streamlit application for auditing property recurring transactions and concessions. This system helps COOs and Auditors detect anomalies, validate fee structures, and identify revenue risks across property management portfolios.

![KPI Overview](https://github.com/user-attachments/assets/c1fe0627-e3ca-4039-b19f-a99e03e8d8f4)

## 🚀 Features

### Data Ingestion
- **📤 File Upload**: Support for PDF, Excel (.xlsx, .xls, .csv), and Word (.docx) files
- **🌐 ResMan API Integration**: Direct sync from ResMan property management system (stub implementation)
- **📊 Intelligent Parsing**: Automatic detection and parsing of ResMan recurring transaction projection reports

### Audit Rules Engine

The system implements comprehensive validation rules:

**A. Lease Cliff Detection**
- Identifies revenue drops > 20% between months
- Highlights potential lease expiration issues
- Risk scoring from 0-100

**B. Concession Misalignment**
- Rent proration mismatch detection
- Concession timing validation
- Excessive concession alerts (>50% of rent)

**C. Recurring Fee Template Validation**
- Validates against standard Village Green fee schedule
- Detects missing recurring charges
- Identifies fee amount mismatches

**D. Employee Unit Conflicts**
- Flags double discount risks
- Identifies employee units with additional concessions

### Analytics & Reporting

**📊 KPI Overview**
- Total Revenue and Net Revenue metrics
- Concession rate tracking
- Finding severity breakdown
- Lease cliff risk indicators

**📉 Revenue Trend Analysis**
- Month-over-month revenue trends
- Visual lease cliff detection
- Concession tapering analysis

**🔍 Unit Drilldown**
- Search and filter by unit or resident
- Detailed transaction history per unit
- Finding attribution to specific units

**⚠️ Audit Findings**
- Severity-based categorization (Critical, High, Medium, Low)
- Detailed explanations with evidence
- Expandable finding details

**📋 Override Panel**
- Mark findings as Reviewed/Overridden/Closed
- Add notes and justifications
- Complete audit trail logging

**📤 Export Functionality**
- Excel export with multiple sheets
- CSV export for findings
- Executive summary generation

## 📋 Requirements

- Python 3.8+
- See `requirements.txt` for full dependency list

## 🛠️ Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/napandya/streamlit-audit-agent-loriaa.git
   cd streamlit-audit-agent-loriaa
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Run the application**
   ```bash
   streamlit run app.py
   ```

4. **Access the application**
   
   Open your browser to `http://localhost:8501`

## 📖 Usage

### Quick Start

1. **Select Data Source**
   - Choose "Upload Files" for ad-hoc analysis
   - Or select "ResMan API Sync" for direct integration

2. **Upload Files** (if using file upload)
   - Click "Browse files" in the sidebar
   - Select one or more files (PDF, Excel, CSV, Word)
   - Files are automatically parsed and analyzed

3. **Set Date Range**
   - Adjust start and end dates in the sidebar
   - Analysis will filter to the selected period

4. **Review Results**
   - Navigate through tabs to explore different views
   - Review KPIs, trends, unit details, and findings

### Working with Findings

**Filter Findings**
- Use sidebar filters to show/hide severity levels
- Filter by finding status (Open, Reviewed, etc.)

**Review a Finding**
1. Go to "Audit Findings" tab
2. Click to expand a finding
3. Review the explanation and evidence
4. Navigate to "Override Panel" to update status

**Override a Finding**
1. Go to "Override Panel" tab
2. Select the finding from the dropdown
3. Choose new status and add notes
4. Enter your name for audit trail
5. Click "Save"

**Export Results**
1. Go to "Export" tab
2. Select data to include in export
3. Enter your name for audit trail
4. Click "Generate Export"
5. Download the file

## 🗂️ Project Structure

```
streamlit-audit-agent-loriaa/
├── app.py                          # Main Streamlit application
├── requirements.txt                # Python dependencies
├── config/
│   ├── settings.py                 # Application configuration
│   └── mappings.yaml               # Category mappings
├── ingestion/
│   ├── pdf_parser.py               # PDF parsing logic
│   ├── excel_parser.py             # Excel/CSV parsing
│   ├── word_parser.py              # Word document parsing
│   ├── resman_client.py            # ResMan API client (stub)
│   └── loader.py                   # Unified file loader
├── models/
│   ├── unit.py                     # Data models (Unit, Transaction, Lease, Finding)
│   └── canonical_model.py          # Data normalization
├── engine/
│   ├── date_range_engine.py        # Date filtering and aggregation
│   ├── rules.py                    # Audit rules implementation
│   ├── anomaly_detector.py         # Anomaly detection orchestrator
│   └── explainability.py           # Human-readable explanations
├── storage/
│   ├── database.py                 # DuckDB persistence (optional)
│   └── audit_log.py                # Audit trail logging
├── ui/
│   ├── filters.py                  # Sidebar filters
│   ├── dashboard.py                # KPI overview
│   ├── charts.py                   # Revenue trend charts
│   ├── unit_view.py                # Unit drilldown
│   ├── findings.py                 # Audit findings table
│   ├── override.py                 # Override panel
│   └── export.py                   # Export functionality
└── utils/
    ├── helpers.py                  # Utility functions
    └── validations.py              # Input validation
```

## 🔧 Configuration

### ResMan API Setup

To connect to ResMan API, set environment variables:

```bash
export RESMAN_API_URL="https://api.resman.com/v1"
export RESMAN_API_KEY="your-api-key"
export RESMAN_PROPERTY_ID="your-property-id"
```

Or update `config/settings.py` directly.

### Fee Template Customization

Edit `config/settings.py` to modify the recurring fee template:

```python
RECURRING_FEE_TEMPLATE = {
    "Billing Fee": 5.00,
    "Cable": 55.00,
    "CAM": 10.00,
    # ... add more fees
}
```

### Category Mapping

Edit `config/mappings.yaml` to customize charge category detection:

```yaml
rent_categories:
  - "Rent"
  - "Base Rent"
  - "Monthly Rent"

concession_categories:
  - "Concession"
  - "Discount"
  # ... add more variations
```

## 📊 Sample Data

The repository includes a sample PDF file: `Recurring Transaction Projection (2).pdf`

This file contains:
- 245 units
- 12 months of recurring transaction data
- Various charge types (rent, fees, concessions)
- Employee unit markers

### Test Results from Sample Data

- **Units Loaded**: 245
- **Transactions**: 7,990
- **Total Revenue**: $175,950.50
- **Concessions**: $9,564.00 (5.4%)
- **Findings Detected**: 144
  - 🔴 Critical: 23 (Double Discount Risk)
  - 🟠 High: 2 (Excessive Concession)
  - 🟡 Medium: 1 (Concession Misaligned)
  - 🟢 Low: 118 (Fee Amount Mismatch, Missing Charges)

## 🎯 Use Cases

### Monthly Property Review
1. Upload latest recurring transaction projection
2. Review KPI dashboard for high-level metrics
3. Check revenue trend for lease cliffs
4. Investigate critical findings
5. Export results for reporting

### Quarterly Audit
1. Set date range to quarter
2. Upload all monthly reports
3. Review all findings
4. Use override panel to document resolutions
5. Export comprehensive audit report

### Fee Validation
1. Upload current recurring charges
2. Filter to "Fee Amount Mismatch" findings
3. Review discrepancies against template
4. Document approved exceptions

## 🔍 Troubleshooting

**Issue**: PDF not parsing correctly
- Ensure PDF is a ResMan recurring transaction projection report
- Check that the format matches expected structure (Unit | Type | Category | Months...)

**Issue**: Large files taking too long
- The app can handle up to 200MB files
- For very large datasets, consider using date range filters

**Issue**: Findings seem incorrect
- Review the audit rules in `engine/rules.py`
- Check category mappings in `config/mappings.yaml`
- Verify fee template in `config/settings.py`

## 🤝 Contributing

Contributions are welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- Built with [Streamlit](https://streamlit.io/)
- PDF parsing with [pdfplumber](https://github.com/jsvine/pdfplumber)
- Charts with [Plotly](https://plotly.com/python/)
- Data processing with [Pandas](https://pandas.pydata.org/)

## 📧 Support

For issues or questions, please open an issue on GitHub or contact the development team.

---

**Village Green Property Audit System** - Making property auditing intuitive and efficient.
