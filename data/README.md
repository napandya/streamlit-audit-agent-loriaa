# ResMan Export Data Folder Guide

This directory holds ResMan CSV exports for the LiveNjoy Residential forensic audit engine.

---

## Subfolder → Report Mapping

| Subfolder | ResMan Report Name | Purpose |
|---|---|---|
| `transactions/` | Transaction List (Credits) | John's Engine: actual concession postings |
| `leases/` | New and Renewed Leases | John's Engine: legally approved concession amounts |
| `edits/` | Edited Transactions by User | Manager Override Audit: reversals and edits |
| `recurring/` | Transaction Projections (Recurring) | Daniel Stage 1: what **should** post each month |
| `rent_rolls/` | Rent Rolls | Daniel Stage 2: what **is** configured per unit |
| `activity/` | Resident Activity | Move-in dates for $0-rent classification |
| `output/` | *(generated)* | Excel audit workbooks written here |

---

## File Naming Convention

Name each export using the **property short code** followed by the report type and period:

```
CAI Transaction List (Credits) - Mar 2026.csv
HP  Transaction List (Credits) - Mar 2026.csv
POT Transaction List (Credits) - Mar 2026.csv
LP  Transaction List (Credits) - Mar 2026.csv
VG  Transaction List (Credits) - Mar 2026.csv
VPA Transaction List (Credits) - Mar 2026.csv
WST Transaction List (Credits) - Mar 2026.csv
```

The loader uses the **first word** of the filename as the property short code, then falls back to keyword matching on the full filename.

---

## Property Short Codes

| Code | Full Property Name |
|---|---|
| `CAI` | Crossings at Irving |
| `POT` | Parks on Taylor |
| `HP` | Highland Park |
| `LP` | La Prada |
| `VG` | Village Green |
| `VPA` | Valencia Plaza |
| `WST` | Western Station |

---

## Preserved Files

- `data/samples/` — sample fixtures used by tests (do **not** move or rename)
- Any flat CSVs already in `data/` (e.g. `CAI Transaction List (Credits) - Feb 2026.csv`) are still loaded by the legacy `utils/data_loader.py` for the AI audit pipeline

---

## Monthly Workflow

1. Export all 6 report types from ResMan for each property.
2. Name each file using the convention above.
3. Drop files into the matching subfolder.
4. Update `AUDIT_MONTH` in `config/fee_schedules.py` (e.g. `"Mar 2026"`).
5. Click **🚀 Run Forensic Audit (v4 Rules)** in the Streamlit sidebar.
6. Find the generated Excel workbook in `data/output/`.
