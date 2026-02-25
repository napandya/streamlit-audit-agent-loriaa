# 🏢 Village Green Property Audit System

A Streamlit application for auditing property recurring transactions and concessions, powered by a LangGraph ReAct agent. It helps COOs and Auditors detect anomalies, validate fee structures, and identify revenue risks across property management portfolios.

![App Screenshot](https://github.com/user-attachments/assets/60f13b2c-94d9-435b-9408-28001afd414a)
![KPI Dashboard](https://github.com/user-attachments/assets/c1fe0627-e3ca-4039-b19f-a99e03e8d8f4)
![Audit Findings](https://github.com/user-attachments/assets/4861ef42-880a-403c-8b84-c8de888e99d0)

---

## 📋 Prerequisites

Make sure the following are installed **before** cloning the repository:

| Prerequisite | Minimum Version | Notes |
|---|---|---|
| Python | 3.11+ | The Dockerfile uses `python:3.11-slim`; 3.8+ may work locally |
| pip | bundled with Python | Used to install dependencies |
| Git | any recent version | To clone the repo |
| Docker *(optional)* | 20.10+ | Only needed if running via container |
| OpenAI API key | — | Required for the LangGraph / LangChain AI agent (`langchain-openai`) |

---

## 🛠️ Installation (Local)

### 1. Clone the repository

```bash
git clone https://github.com/napandya/streamlit-audit-agent-loriaa.git
cd streamlit-audit-agent-loriaa
```

### 2. Create and activate a virtual environment (recommended)

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

Key packages installed:

| Package(s) | Purpose |
|---|---|
| `streamlit>=1.31.0` | Web UI framework |
| `pandas`, `openpyxl` | Data processing |
| `pdfplumber` | PDF parsing |
| `python-docx` | Word document parsing |
| `plotly` | Interactive charts |
| `langgraph`, `langchain`, `langchain-openai`, `langchain-core` | AI audit agent |
| `duckdb` | Optional local persistence |
| `reportlab` | PDF report generation |
| `pytest`, `pytest-mock` | Test suite |

---

## 🔐 Environment Variables / Secrets

Before running the app, export the following environment variables (or add them to a `.env` file):

```bash
export OPENAI_API_KEY="sk-..."           # Required for the AI agent

# Optional — only if connecting to ResMan API:
export RESMAN_API_URL="https://api.resman.com/v1"
export RESMAN_API_KEY="your-api-key"
export RESMAN_PROPERTY_ID="your-property-id"
```

---

## 🚀 Running the App (Local)

```bash
streamlit run app.py
```

Then open **http://localhost:8501** in your browser.

> **Sample data included:** A sample PDF (`Recurring Transaction Projection (2).pdf`) is included in the repo. Upload it on first launch to see the app with real data (245 units, 12 months, 7,990 transactions).

---

## 🐳 Running with Docker

```bash
# Build the image
docker build -t streamlit-audit-agent .

# Run the container (pass your OpenAI key)
docker run -p 8501:8501 \
  -e OPENAI_API_KEY="sk-..." \
  streamlit-audit-agent
```

Then open **http://localhost:8501**.

> The Dockerfile already exposes port 8501 and includes a health-check endpoint at `/_stcore/health`.

---

## 🧪 Running the Test Suite

```bash
pytest tests/
```

---

## ✨ Features

### 📤 Data Ingestion
- **Multi-format file upload**: Support for PDF, Excel (`.xlsx`, `.xls`, `.csv`), and Word (`.docx`) files
- **ResMan API integration**: Direct sync from ResMan property management system (stub ready for production)
- **Intelligent parsing**: Automatic detection and parsing of ResMan recurring transaction projection reports

### 🔍 Audit Rules Engine

| Rule | Description |
|---|---|
| **Lease Cliff Detection** | Identifies revenue drops > 20% between months; risk scoring 0–100 |
| **Concession Misalignment** | Detects rent proration mismatches, concession timing issues, and excessive concessions (>50% of rent) |
| **Fee Template Validation** | Validates charges against the Village Green fee schedule; flags missing or mismatched fees |
| **Employee Unit Conflicts** | Flags employee units with additional concessions (double discount risk) |

### 📊 Analytics & Reporting
- **KPI Overview** — total revenue, net revenue, concession rate, finding severity breakdown, lease cliff indicators
- **Revenue Trend Analysis** — month-over-month trends with visual lease cliff detection
- **Unit Drilldown** — search/filter by unit or resident; detailed transaction history
- **Audit Findings** — severity-based categorisation (Critical → Low) with expandable details
- **Override Panel** — mark findings as Reviewed / Overridden / Closed; complete audit trail
- **Export** — Excel (multi-sheet), CSV, and executive summary PDF

---

## 🗂️ Project Structure

```
streamlit-audit-agent-loriaa/
├── app.py                          # Main Streamlit application
├── requirements.txt                # Python dependencies
├── Dockerfile                      # Container build definition
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
├── agents/                         # LangGraph ReAct agent definitions
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
├── utils/
│   ├── helpers.py                  # Utility functions
│   └── validations.py              # Input validation
└── tests/                          # pytest test suite
```

---

## 🔧 Configuration

### ResMan API Setup

Set the following environment variables to connect to a live ResMan instance:

```bash
export RESMAN_API_URL="https://api.resman.com/v1"
export RESMAN_API_KEY="your-api-key"
export RESMAN_PROPERTY_ID="your-property-id"
```

Or update `config/settings.py` directly.

### Fee Template Customisation

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

Edit `config/mappings.yaml` to customise charge category detection:

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

---

## 🔍 Troubleshooting

**PDF not parsing correctly**
- Ensure the PDF is a ResMan recurring transaction projection report.
- Check that the format matches the expected structure: `Unit | Type | Category | Months…`

**Large files taking too long**
- The app can handle files up to 200 MB.
- For very large datasets, apply date range filters before uploading.

**Findings seem incorrect**
- Review the audit rules in `engine/rules.py`.
- Check category mappings in `config/mappings.yaml`.
- Verify the fee template in `config/settings.py`.

---

## 🤝 Contributing

Contributions are welcome!

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/my-change`)
3. Make your changes and add tests
4. Submit a pull request

---

## 📝 License

This project is licensed under the Apache License 2.0 — see the [LICENSE](LICENSE) file for details.