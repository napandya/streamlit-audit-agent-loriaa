# v4 Integration Architecture Guide

## 1. Overview

This integration merges the v4 forensic audit engine (`v4/LNJ-Audit-v4/`) into the
root modular package structure. The v4 engine — John's 9 concession rules, Daniel's
2-stage revenue integrity engine, the fee schedule check, manager override leaderboard,
and exposure drilldowns — is now available as a set of proper Python modules. The
existing AI/LangGraph audit pipeline, file-upload UI, and all supporting packages are
preserved **completely unchanged**.

---

## 2. Architecture: Before vs After

| Aspect | Before (root only) | After (integrated) |
|---|---|---|
| Audit rules | Generic concession rules in `engine/rules.py` / `engine/concession_audit.py` | John's 9 + Daniel's 2-stage in `engine/resman_rules.py` |
| Data ingestion | File-upload UI + flat CSV scan | File-upload **+** 6-subfolder ResMan loader |
| Fee schedule | Village Green only in `config/settings.py` | All 7 properties in `config/fee_schedules.py` |
| Property mapping | None | CAI, POT, HP, LP, VG, VPA, WST in `config/fee_schedules.py` |
| Manager overrides | None | `engine/resman_rules.run_manager_override_audit` |
| Exposure drilldowns | None | `engine/resman_rules.calculate_exposure` |
| Excel export | None | `ui/export.export_audit_workbook` |
| UI tabs | Rent Roll, Projections, AI Findings, Full Report, Prompt Editor, Raw Data | All above + 6 forensic tabs |

---

## 3. New Files Added

| File | Purpose | v4 Source |
|---|---|---|
| `config/fee_schedules.py` | All 7 property fee schedules + audit constants | `v4/LNJ-Audit-v4/audit_bot.py` (constants section) |
| `ingestion/resman_csv_loader.py` | Multi-subfolder CSV loader | `v4/LNJ-Audit-v4/audit_bot.py` (loader section) |
| `engine/resman_rules.py` | John's 9 rules + Daniel's 2-stage engine + fee check + orchestrator | `v4/LNJ-Audit-v4/audit_bot.py` |
| `ui/tabs/revenue_integrity_tab.py` | Revenue Integrity tab (Daniel's engine) | `v4/LNJ-Audit-v4/app.py` (Tab 3) |
| `ui/tabs/overrides_tab.py` | Manager Overrides tab | `v4/LNJ-Audit-v4/app.py` (Tab 4) |
| `ui/tabs/exposure_tab.py` | Exposure Drilldowns tab | `v4/LNJ-Audit-v4/app.py` (Tab 5) |
| `ui/tabs/fee_schedule_tab.py` | Fee Schedule Check tab | `v4/LNJ-Audit-v4/app.py` (Tab 7) |
| `v4_integration.md` | This document | — |
| `data/transactions/.gitkeep` | Placeholder — Transaction List CSVs go here | — |
| `data/leases/.gitkeep` | Placeholder — New & Renewed Leases CSVs go here | — |
| `data/edits/.gitkeep` | Placeholder — Edited Transactions CSVs go here | — |
| `data/recurring/.gitkeep` | Placeholder — Transaction Projections CSVs go here | — |
| `data/rent_rolls/.gitkeep` | Placeholder — Rent Roll CSVs go here | — |
| `data/activity/.gitkeep` | Placeholder — Resident Activity CSVs go here | — |
| `data/output/.gitkeep` | Placeholder — generated Excel workbooks land here | — |

---

## 4. Modified Files

| File | What Changed |
|---|---|
| `app.py` | Added `resman_results` session state key; added **🚀 Run Forensic Audit** sidebar button; added 6 new tabs (Executive Summary, Concession Audit (John), Revenue Integrity (Daniel), Manager Overrides, Exposure Drilldowns, Fee Schedule Check) |
| `ui/tabs/concession_tab.py` | Added `johns_flags` parameter to `render_concession_tab`; added `_render_johns_flags` helper for v4 schema; legacy path preserved |
| `ui/export.py` | Added `export_audit_workbook` and `render_excel_download_button` functions |
| `data/README.md` | Replaced stub with full subfolder setup guide |

---

## 5. Untouched Files

The following files were **not modified** in any way:

- `agents/` — LangGraph ReAct agent (untouched)
- `engine/langgraph_engine.py` — LangGraph engine (untouched)
- `engine/concession_audit.py` — legacy concession auditor (untouched)
- `engine/anomaly_detector.py` — statistical anomaly detection (untouched)
- `engine/rules.py` — generic rules (untouched)
- `engine/date_range_engine.py` — date range engine (untouched)
- `engine/explainability.py` — explainability engine (untouched)
- `ingestion/loader.py` — file loader (untouched)
- `ingestion/resman_client.py` — ResMan API client (untouched)
- `ingestion/resman_transaction_parser.py` — transaction parser (untouched)
- `ingestion/parsers/` — all parsers (untouched)
- `storage/` — database and audit log (untouched)
- `models/` — canonical model (untouched)
- `config/settings.py` — existing settings (untouched)
- `utils/` — all utilities (untouched)
- `audit_engine.py` — projection metrics (untouched)

---

## 6. Data Folder Setup

1. Export the 6 report types from ResMan for all properties.
2. Name each file using the property short code convention:
   ```
   CAI Transaction List (Credits) - Mar 2026.csv  → data/transactions/
   HP  New and Renewed Leases.csv                  → data/leases/
   VG  Edited Transactions by User.csv             → data/edits/
   WST Recurring Transaction Projection.csv        → data/recurring/
   POT Rent Roll.csv                               → data/rent_rolls/
   LP  Resident Activity.csv                       → data/activity/
   ```
3. Update `AUDIT_MONTH` in `config/fee_schedules.py` to the current period (e.g. `"Mar 2026"`).
4. Run the forensic audit (see Section 7).
5. Generated Excel workbooks appear in `data/output/`.

---

## 7. How to Run

### AI Audit (existing pipeline)
1. Upload rent roll, projection, or concession CSV/PDF/Word files via the **📤 Upload Files** sidebar widget.
2. Enter your OpenAI API key.
3. Click **🚀 Run AI Audit**.
4. Review findings in the **AI Findings**, **Full Report**, and **Prompt Editor** tabs.

### Forensic Rules Audit (new v4 pipeline)
1. Drop ResMan export CSVs into the 6 subfolders under `data/` (see Section 6).
2. Click **🚀 Run Forensic Audit (v4 Rules)** in the sidebar.
3. Six new tabs appear instantly:
   - **📈 Executive Summary** — KPI metrics + filterable exceptions table
   - **🔍 Concession Audit (John)** — John's 9 rules, unit-level flags
   - **⚙️ Revenue Integrity (Daniel)** — Stage 1 (projection) + Stage 2 (rent roll)
   - **👤 Manager Overrides** — leaderboard + raw edit log
   - **💰 Exposure Drilldowns** — by property / rule / risk / manager
   - **📋 Fee Schedule Check** — per-property fee amount validation

---

## 8. The Two Audit Pipelines

| | AI Audit | Forensic Rules Audit |
|---|---|---|
| **Input** | Uploaded files (any format) | Pre-placed CSVs in 6 subfolders |
| **Engine** | LangGraph ReAct + OpenAI LLM | Deterministic Python rules |
| **Output** | Free-form narrative analysis | Structured flag DataFrames |
| **Reproducibility** | Varies (LLM) | 100% deterministic |
| **Speed** | ~30–90 seconds | <5 seconds |
| **Best for** | Cross-property patterns, narrative | Compliance checklists, export |

The two pipelines are **complementary**: run the forensic audit first to generate
structured flags, then run the AI audit to get expert narrative commentary on top of
the same data.

---

## 9. Audit Constants

All constants live in `config/fee_schedules.py`:

| Constant | Value | Controls |
|---|---|---|
| `AUDIT_MONTH` | `"Mar 2026"` | Which month column to extract from Transaction Projection |
| `APPROVED_CODES` | `{"CONR","CRTCO","EMPL","MCCR","RRFee"}` | Valid concession transaction codes |
| `CONCESSION_CRITICAL_AMT` | `700` | Single credit ≥ $700 → CRITICAL flag |
| `CONCESSION_HIGH_AMT` | `500` | Recurring > $500 for 2+ months → HIGH flag |
| `STANDARD_CHARGE_THRESHOLD` | `0.90` | 90% of units must have a standard charge |
| `RECENT_MOVEIN_DAYS` | `60` | Move-in within 60 days → $0 net rent is OK |
| `OPTIONAL_CHARGE_KEYWORDS` | carport, parking, pet rent, … | Charges exempt from 90% rule |
| `RISK_CRITICAL` | `"CRITICAL"` | Risk level label |
| `RISK_HIGH` | `"HIGH"` | Risk level label |
| `RISK_MEDIUM` | `"MEDIUM"` | Risk level label |

---

## 10. 7 Properties Reference

| Code | Full Name | Fee Schedule |
|---|---|---|
| `CAI` | Crossings at Irving | ✅ |
| `POT` | Parks on Taylor | ✅ |
| `HP` | Highland Park | ✅ |
| `LP` | La Prada | ✅ |
| `VG` | Village Green | ✅ |
| `VPA` | Valencia Plaza | ✅ |
| `WST` | Western Station | ✅ |
