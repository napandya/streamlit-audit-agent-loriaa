# LiveNJoy LLC — Concession Audit System

A Streamlit application that audits ResMan Transaction List (Credits) CSVs using a **hybrid deterministic + AI pipeline**. A deterministic rules engine pre-scans every CSV for 8 anomaly patterns, then a LangGraph ReAct agent (OpenAI o3) narrates the findings into an executive audit report.

Built for COOs and Auditors managing multi-property portfolios.

---

## How It Works

```
CSV files (data/)
    │
    ▼
ConcessionRulesEngine          ← 8 rules (CONC-001 … CONC-008)
    │
    ├─► Structured findings
    └─► Per-property stats
            │
            ▼
      format_for_llm()         ← stats + ≤5 evidence rows / finding
            │
            ▼
   LangGraph ReAct Agent       ← OpenAI o3, 16 384 tokens
            │
            ▼
      Merge & Dedup
            │
            ▼
   Findings Tab + Report Tab
```

### Deterministic Rules

| Rule | Severity | Description |
|------|----------|-------------|
| CONC-001 | HIGH | Excessive single concession (> $1 000) |
| CONC-002 | HIGH | $999 special-rate concession |
| CONC-003 | MEDIUM | Move-in special ($99 / $0) |
| CONC-004 | MEDIUM/HIGH | Reversed concession (Reverse Date populated) |
| CONC-005 | MEDIUM | Duplicate unit concession in same period |
| CONC-006 | LOW | Generic / vague description |
| CONC-007 | HIGH | Property total > 2× median across all properties |
| CONC-008 | MEDIUM | Negative amount (data-entry error) |

---

## Prerequisites

- **Python 3.13+**
- **OpenAI API key** (required for AI narration; deterministic audit works without it)

---

## Quick Start — Windows (PowerShell)

```powershell
# Clone the repository
git clone https://github.com/napandya/streamlit-audit-agent-loriaa.git
cd streamlit-audit-agent-loriaa

# Create and activate a virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt

# Run the app
streamlit run app.py
```

Then open **http://localhost:8501** in your browser.

> **Note:** If PowerShell blocks the activate script, run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` first.

---

## Quick Start — macOS / Linux (Bash)

```bash
# Clone the repository
git clone https://github.com/napandya/streamlit-audit-agent-loriaa.git
cd streamlit-audit-agent-loriaa

# Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run the app
streamlit run app.py
```

Then open **http://localhost:8501** in your browser.

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENAI_API_KEY` | For AI audit | OpenAI API key (can also be entered in the sidebar at runtime) |

Set it before launching:

```powershell
# Windows PowerShell
$env:OPENAI_API_KEY = "sk-..."
```

```bash
# macOS / Linux
export OPENAI_API_KEY="sk-..."
```

---

## Running with Docker

```bash
# Build the image
docker build -t streamlit-audit-agent .

# Run the container
docker run -p 8501:8501 \
  -e OPENAI_API_KEY="sk-..." \
  streamlit-audit-agent
```

Then open **http://localhost:8501**.

> The Dockerfile uses `python:3.13-slim`, exposes port 8501, and includes a health check at `/_stcore/health`.

---

## Deploying to Streamlit Community Cloud (Free)

1. Push this repository to GitHub (public or private).

2. Go to [share.streamlit.io](https://share.streamlit.io) and sign in with GitHub.

3. Click **New app** and select:
   - **Repository:** `napandya/streamlit-audit-agent-loriaa`
   - **Branch:** `main`
   - **Main file path:** `app.py`

4. Under **Advanced settings → Secrets**, add:
   ```toml
   OPENAI_API_KEY = "sk-..."
   ```

5. Click **Deploy**. The app will be live at `https://<your-app>.streamlit.app`.

> **Data:** The 7 CSV files in `data/` are committed to the repo and auto-loaded on startup — no manual upload needed.

---

## Running the Test Suite

```bash
pytest tests/
```

---

## Key Packages

| Package(s) | Purpose |
|---|---|
| `streamlit>=1.31.0` | Web UI framework |
| `pandas`, `openpyxl` | Data processing |
| `pdfplumber` | PDF parsing |
| `python-docx` | Word document parsing |
| `plotly` | Interactive charts |
| `langgraph`, `langchain`, `langchain-openai`, `langchain-core` | LangGraph ReAct agent |
| `duckdb` | Optional local persistence |
| `reportlab` | PDF report generation |
| `pytest`, `pytest-mock` | Test suite |

---

## Project Structure

```
streamlit-audit-agent-loriaa/
├── app.py                          # Main Streamlit entry point
├── audit_engine.py                 # Metrics computation helpers
├── requirements.txt                # Python dependencies
├── Dockerfile                      # Container build
├── agents/
│   └── audit_agent.py              # LangGraph ReAct agent (4 tools, o3)
├── config/
│   ├── settings.py                 # App configuration
│   └── mappings.yaml               # Category mappings
├── data/
│   └── *.csv                       # 7 ResMan Transaction List CSVs
├── engine/
│   ├── concession_rules.py         # ★ Deterministic rules (CONC-001 … CONC-008)
│   ├── langgraph_engine.py         # ★ Hybrid pipeline orchestrator
│   ├── rules.py                    # Legacy rules engine
│   ├── anomaly_detector.py         # Anomaly detection
│   └── explainability.py           # Human-readable explanations
├── ingestion/
│   ├── loader.py                   # Unified file loader
│   └── parsers/                    # CSV, PDF, Excel, Word parsers
├── models/                         # Unit, Transaction, Canonical models
├── storage/                        # DuckDB + audit log
├── ui/
│   ├── tabs/                       # Findings, Report, Rent Roll, Projection
│   └── *.py                        # Dashboard, charts, filters, export
├── utils/                          # Helpers, data processor, validations
└── tests/                          # pytest test suite
```

---

## Architecture Diagram

See [streamlit_app.md](streamlit_app.md) for full Mermaid architecture and sequence diagrams.

---

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/my-change`)
3. Make your changes and add tests
4. Submit a pull request

---

## License

This project is licensed under the Apache License 2.0 — see the [LICENSE](LICENSE) file for details.