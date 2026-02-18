# 🏢 Village Green Property Audit System

A comprehensive Streamlit application for auditing property recurring transactions and concessions.

![App Screenshot](https://github.com/user-attachments/assets/60f13b2c-94d9-435b-9408-28001afd414a)
![KPI Dashboard](https://github.com/user-attachments/assets/c1fe0627-e3ca-4039-b19f-a99e03e8d8f4)
![Audit Findings](https://github.com/user-attachments/assets/4861ef42-880a-403c-8b84-c8de888e99d0)

## Quick Start

```bash
pip install -r requirements.txt
streamlit run app.py
```

Then open http://localhost:8501 and upload the sample PDF: `Recurring Transaction Projection (2).pdf`

## Features

✅ **Multi-format file upload** (PDF, Excel, Word)  
✅ **ResMan API integration** (stub ready for production)  
✅ **7 audit rules** detecting lease cliffs, concessions, fees, and conflicts  
✅ **Interactive dashboards** with KPIs, trends, and unit drilldowns  
✅ **Audit trail** with override capabilities  
✅ **Export to Excel/CSV** with executive summaries

## Documentation

See [README_USAGE.md](README_USAGE.md) for comprehensive documentation including:
- Detailed feature descriptions
- Configuration guide
- Usage examples
- Troubleshooting tips

## Architecture

See [streamlit_app.md](streamlit_app.md) for the complete architecture documentation.

## License

MIT License - see [LICENSE](LICENSE) file for details.