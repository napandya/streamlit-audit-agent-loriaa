# LNJ Audit Bot — Full Project Context
**Last updated:** May 1, 2026 — Final April 2026 report generated from full Apr 1–30 CSVs and sent to John Barajas. Awaiting his sign-off.
**Paste this into a new Copilot Chat to resume exactly where we left off.**

---

## What This Project Is

An automated ResMan Concession & Revenue Integrity Audit Bot for **LiveNjoy Residential**.  
It reads 6 types of CSV exports from ResMan, runs three audit engines (John B.'s concession rules + Daniel Twito's 2-stage revenue integrity audit + Fee Schedule Check), and outputs an interactive Streamlit dashboard + timestamped Excel report.

---

## Environment

- **Folder:** `D:\Loriaa Projects\March\LNJ-Audit-v4\`
- **Python:** 3.11.9 — virtual environment at `.venv`
- **Packages:** pandas, numpy, openpyxl, streamlit 1.54.0, python-docx
- **Run the bot:** `.venv\Scripts\python.exe audit_bot.py`
- **Run the dashboard:** `.venv\Scripts\streamlit.exe run app.py` → http://localhost:8501

---

## Files

| File | Purpose |
|---|---|
| `audit_bot.py` | Core engine — all ingestion, rules, Excel export |
| `app.py` | Streamlit dashboard — **7 tabs** |
| `diagnose.py` | Scratch diagnostic script — safe to edit/delete |
| `data/transactions/` | Transaction List CSVs (7 files, one per property) |
| `data/leases/` | New & Renewed Leases CSVs (7 files) |
| `data/edits/` | Edited Transactions by User CSVs (7 files) |
| `data/recurring/` | Recurring Transaction Projection CSVs (7 files) |
| `data/rent_rolls/` | Rent Roll CSVs (7 files) |
| `data/activity/` | Resident Activity CSVs (7 files) |
| `output/` | Timestamped Excel exports saved here |

**Fee Sheet Source Files:** `D:\Loriaa Projects\Feb 2026 Source Files\Fee Details\`  
(6 .docx files — one per property. All 7 properties now have fee schedules hardcoded into `PROPERTY_FEE_SCHEDULE` in `audit_bot.py`. La Prada fees added March 11, 2026.)

**`Fee Schedules.md`** — printable fee sheet reference for all 7 properties (created March 11, 2026).

**Total: 42 CSV files, all load successfully (42/42).**

---

## 7 Properties

| Code | Full Name |
|---|---|
| CAI | Crossings at Irving |
| POT | Parks on Taylor |
| HP | Highland Park |
| LP | La Prada |
| VG | Village Green |
| VP / VPA | Valencia Plaza |
| WST | Western Station |

---

## Audit Month

`AUDIT_MONTH = "Mar 2026"` — update this constant in `audit_bot.py` each month.

---

## Key Constants in audit_bot.py

```python
APPROVED_CODES            = {"CONR", "CRTCO", "EMPL", "MCCR", "RRFee"}
CONCESSION_CRITICAL_AMT   = 700.0    # single credit >= $700 → CRITICAL
STANDARD_CHARGE_THRESHOLD = 0.90     # 90% rule for Daniel Stage 1
RECENT_MOVEIN_DAYS        = 60       # days after move-in to suppress $0 rent flag
AUDIT_MONTH               = "Mar 2026"

# Per Daniel: parking, pet fees, washer/dryer are optional (unit-specific add-ons)
# — excluded from Missing Standard Charge rule
OPTIONAL_CHARGE_KEYWORDS  = {"carport", "parking", "pet rent", "pet fee",
                              "washer", "dryer", "first floor", "1st floor"}
```

---

## John's Engine — run_johns_engine()

Uses **Rent Roll concession rows** (negative-amount lines with concession keywords) as the "approved concession" source. LiveNjoy stores approved concessions as discounted rent line items on the Rent Roll, NOT in a separate Rec_Conc field (Rec_Conc = $0 for all lease rows — this is a ResMan data reality).

| Rule | Name | Risk | Description |
|---|---|---|---|
| R1 | Post-Term Credit | CRITICAL | Credit posted after lease end date |
| R2 | Missing Lease | HIGH | Credit posted but no lease on file |
| R3 | Large Credit ≥$700 | CRITICAL | Single credit at or above threshold |
| ~~R4~~ | ~~Invalid Credit Code~~ | ~~HIGH~~ | **DISABLED March 10, 2026** — John confirmed descriptions are freeform identifiers with no standard rule. No approved keyword list exists. |
| R5 | Missing Addendum | CRITICAL | Credit in Transaction List but NO concession row on Rent Roll |
| R6 | Amount Mismatch | HIGH | Rent Roll concession ≠ Transaction List credit (>10% and >$10 delta) |
| R7 | Not Properly Posted | HIGH | Rent Roll has concession setup but nothing posted in Transaction List |

**Last run results (Feb 2026):** 198 flags (60 Missing Addendum, 42 Large Credit, 25 Amount Mismatch, 68 Invalid Code, 2 Missing Lease, 1 Post-Term)  
**R4 now disabled** — Invalid Code flags will no longer appear in future runs.

---

## ⚠️ Critical Bug Fixed — April 30, 2026

**Bug 1 (ROOT CAUSE — load_transaction_list):**  
ResMan Transaction List CSVs contain multiple section types: `Credit`, `Charge`, `Payment`, `Deposit Applied to Balance`, `Deposit Refund`, `Deposit - Security Deposit`, `Payment - Payment On Behalf Of Resident`.

The section forward-fill (`ffill()`) only reassigned `_section` when rows matched `^(Credit|Charge) - `.  
All other section headers (Payment, Deposit, etc.) left `_section = NaN`, which `ffill()` silently replaced with the last Credit section label.  
Result: **every payment and deposit row in the file was classified as a Credit and ingested as a concession** — up to 340 payment rows per property (1,456+ total across 7 properties).

This caused:
- R5 "Missing Addendum" to fire for every unit making a payment (no RR concession setup exists for a payment)
- R3 "Large Credit ≥$700" to fire for every rent payment ≥$700
- R2 "Missing Lease" to fire for some payment-bearing units
- Daniel's "Manual Posting Without Setup" to fire similarly
- Confirmed example: unit 0313 Village Green (Tuesday Greene) had $1,862.21 payment flagged as a missing-addendum credit

**Fix:** Changed the section detection regex from `r"^(Credit|Charge) - "` to `r"^(Credit|Charge|Payment|Deposit)"` so ALL section header types properly reset the `_section` column and prevent Payment/Deposit rows from inheriting a Credit label.

**Bug 2 (run_daniels_engine — Posted vs Recurring Mismatch):**  
The Projection rent query used `r"\brent\b"` which also matched `Concession - Rent` category rows (negative amounts). These were subtracted from `recurring_rent`, making it artificially low vs. the Rent Roll's rent-only `posted_rent`. Result: every unit with a concession setup generated a false "Posted vs Recurring Mismatch" flag.

**Fix:** Added `~contains("concession")` and `(Amount > 0)` filters to the Projection rent query so it reflects gross rent only — matching how `posted_rent` is computed from the Rent Roll.

**Bug 6 — R5 Missing Addendum rule disabled (April 30, 2026, per John):**  
John confirmed that all flagged addenda exist — they are saved as PDFs in ResMan's Documents section, which is not accessible from CSV exports. The Rent Roll concession row is not a reliable proxy for addendum existence.  

**Fix:** R5 is now fully disabled. The `if in_tx and not in_rr` block is commented out. The rule will not fire until a data source for addendum status becomes available (e.g. a ResMan document API or a manual tracker John provides).
`Credit - Resident Referral` transactions (one-time referral bonuses) were being evaluated by the R5 Missing Addendum cross-check. Since referral credits never have a Rent Roll concession row by design, every referral credit generated a false CRITICAL "Missing Addendum" flag.  

**Fix:** Added `Credit - Resident Referral` to a skip-set (`_R5_SKIP_SECTIONS`) in `run_johns_engine()`. This section is now excluded from the `tx_credit_lookup` so it cannot trigger R5.  
NOTE: `_section` column is now preserved on `df_trans` (not dropped in `load_transaction_list`) so engines can filter by section type.

**Bug 3B (R5 Missing Addendum — Employee Unit Rent Allowance false positive):**  
`Credit - Employee Unit Rent Allowance` transactions (HR-approved employee unit discounts, code `EMPL`) were also being evaluated by R5. These never have a Rent Roll concession row setup in the standard way. Result: multiple false CRITICAL flags per employee unit each month.  

**Fix:** Added `Credit - Employee Unit Rent Allowance` to the same `_R5_SKIP_SECTIONS` set.  
Employee unit credits are still audited via Daniel's "Manual Posting Without Setup" rule, which correctly flags them when they lack a Projection concession row setup.

**Bug 5 (Fee Schedule Check — multi-space optional fees flagged as violations):**  
Units renting multiple parking spaces (e.g. 3 × $35 = $105/mo at Crossings at Irving) were flagged as "Fee Schedule Violation" because the check compared the unit's total parking charge against the single-space schedule rate ($35), producing a $70 variance.  

**Fix:** For `optional: True` fees in `PROPERTY_FEE_SCHEDULE`, the check now skips if the unit's charge is an exact whole multiple of the per-unit fee rate (i.e. `actual_amt % fee_amount == 0`). Mandatory fees (Billing, Trash, Pest, etc.) are not affected.  
Example: CAI Units 157 ($105) and 222 ($105) are now correctly skipped. CAI Unit 181 ($100) is still flagged — $100 is not an exact multiple of $35.

**One rule still NOT implemented** — "Incorrect Frequency Setup" — requires a separate data source showing approved concession term (one-time / 12-month / MTM). ResMan does not export this. Still waiting on John to provide a tracker.

---

## Daniel's Engine — run_daniels_engine()

### Stage 1 — Recurring Transaction Projection

| Rule | Risk | Description |
|---|---|---|
| Missing Standard Charge | HIGH | Charge present on <90% of units (optional charges excluded — see whitelist) |
| Major Charge Amount Variance | HIGH | Unit charge varies ≥20% AND ≥$5 from property standard (grouped by Unit_Type) |
| Minor Charge Amount Variance | MEDIUM | Any charge variance ≥$1 (per Daniel's confirmed $1 cutoff) |
| Concession >$500 for 2+ Months | HIGH | Recurring large concession |
| Concession No Expiration | MEDIUM | Concession with no end date |

**Important:** Variance is grouped by `["Property", "Unit_Type", "Category"]` — prevents false positives from comparing 1BR vs 2BR charges.

**Variance threshold updated March 4, 2026:** Changed from `$5 / 10%` to **`$1`** per Daniel's confirmation.  
**Optional charge whitelist added:** Carport/Parking, Pet Rent/Fee, Washer/Dryer, First Floor exempt from Missing Standard Charge.

### Stage 2 — Posted Rent Roll Audit

Filtered to **occupied units only** (Status: C, MTM, NTV).

| Rule | Risk | Description |
|---|---|---|
| $0 Net Rent (Not Recent) | CRITICAL | Occupied unit net rent = $0, moved in >60 days ago |
| $0 Net Rent (Recent Move-in) | MEDIUM | Same but recent move-in |
| Negative Net Rent | CRITICAL | Net rent < $0 |
| Manual Posting Without Setup | HIGH | Credit in TX list but no concession in Projection |
| Posted vs Recurring Mismatch | HIGH | Posted rent ≠ recurring projection rent |
| Misc Tenant Credit | HIGH | Misc tenant credit posted |

**Last run results (March 4):** 956 flags

---

## Fee Schedule Check — run_fee_schedule_check() ← NEW March 4, 2026

New engine added based on fee sheet .docx files Daniel provided.

Compares each unit's existing recurring charges (from Recurring Projection) against the official fee sheet amounts in `PROPERTY_FEE_SCHEDULE`. Flags any charge that **exists at the wrong amount** (≥$1 variance). Missing charges are handled by the 90% rule, not here.

| Rule | Risk | Description |
|---|---|---|
| Fee Schedule Violation | HIGH | Charge exists on Recurring Projection but amount differs from official fee sheet by ≥$1 |

**Fee schedule loaded for all 7 properties** (La Prada added March 11, 2026):

| Property | Key monthly fees |
|---|---|
| Crossings at Irving | Billing $5, Trash $10, Pest $8, Package Locker $9, Internet $55, First Floor $25 |
| Highland Park | Billing $5, Trash $15, Pest $5, Valet Trash $35 |
| La Prada | Billing $5, Trash $10, Package Locker $7.50, Pest $6 |
| Parks on Taylor | Billing $5, Trash $15, Pest $5, CAM $10 |
| Valencia Plaza | Billing $5, Trash $10, Pest $6 |
| Village Green | Billing $5, Trash $10, Pest $8, CAM $10, Valet Trash $35, HOA $2.50, Package Locker $9, Internet $55 |
| Western Station | Billing $5, Trash $10, Pest $10, CAM $10, Valet Trash $35, Package Locker $9 |

Optional (not flagged if missing, only flagged if wrong amount): Parking, Pet Rent, Washer/Dryer, First Floor.

**Last run results:** 172 flags.

---

## Override Audit

Reads the Edited Transactions by User files, tracks all manager reversals and amount changes.  
**Last run:** 27 managers | 1,044 events | $-236,414.24 revenue impact

---

## Last Full Run Results (May 1, 2026 @ 13:42) — FINAL APRIL 2026 OUTPUT — sent to John

```
42/42 files loaded (full Apr 1–30, 2026 CSVs from Daniel)
375   transaction rows
69    John flags
302   Daniel flags
169   Fee Schedule flags
15    managers | 1,225 events | $-221,888.56 revenue impact
281   units audited | 540 total exceptions
$95,729.96 total exposure | 19 CRITICAL flags
Output: output/LNJ_Audit_20260501_1342.xlsx
```

Verification (verify_final.py): 7/8 checks passed. All of John's reported issues confirmed resolved.
Awaiting John's sign-off.

### Previous Run (April 30, 2026 @ 12:25) — POST R5 DISABLE (superseded)

```
42/42 files loaded
375   transaction rows (Credit sections only — payment rows correctly excluded)
95    John flags
302   Daniel flags
194   Fee Schedule flags
16    managers | 514 events | $-105,396.31 revenue impact
284   units audited | 591 total exceptions
$103,338.16 total exposure | 56 CRITICAL flags
Output: output/LNJ_Audit_20260430_1119.xlsx
```

### Previous Run (March 11, 2026 @ 13:41) — BUGGY OUTPUT (do not use)

```
42/42 files loaded
3,676 John flags  ← caused by Bug 1 (payment rows leaking into credits)
964   Daniel flags
218   Fee Schedule flags
16    managers | 359 events | $-63,702.03 revenue impact
629   units audited | 4,858 total exceptions
$7,286,676.98 total exposure | 2,691 CRITICAL flags
Output: output/LNJ_Audit_20260311_1341.xlsx
```

⚠️ NOTE: John flag count jumped from 198 → 3,676. Suspected cause: March Transaction List
export includes full transaction history (not just March), causing historical transactions
to be re-flagged. Confirm date range with Daniel — Transaction List should be Mar 1–11, 2026 only.

**Root cause confirmed April 30, 2026:** The 3,676 was NOT a date-range issue.
It was Bug 1 (payment rows leaking into credits — see above). March files happened to have
similar file structure; April files exposed it clearly. The bug existed in all prior runs.

### Previous Run (Feb 2026 — March 4, 2026 @ 11:53)
```
42/42 files loaded
198   John flags
956   Daniel flags
172   Fee Schedule flags
27    managers | 1,044 override events | $-236,414.24 revenue impact
515   units audited | 1,326 total exceptions
$277,471.28 total exposure | 110 CRITICAL flags
Output: output/LNJ_Audit_20260304_1153.xlsx
```

---

## Dashboard Tabs (app.py) — 7 tabs

| Tab | Content |
|---|---|
| 1 — Executive Summary | KPIs + all exceptions with filters |
| 2 — Concession Audit (John) | Rule summary + unit-level flags |
| 3 — Revenue Integrity (Daniel) | Stage 1 (projection) + Stage 2 (rent roll) sub-tabs |
| 4 — Manager Overrides | Leaderboard + raw override log |
| 5 — Exposure Drilldowns | By property / rule / risk / manager |
| 6 — Risk Matrix | Heatmap + resident-level drilldown |
| **7 — Fee Schedule Check** | **NEW — per-property summary + unit detail + fee reference table** |

---

## Resolution Workflow — Excel Checklist (added March 4, 2026)

All four flag sheets in the Excel export now have two prepended columns:

| Column | Default | Options |
|---|---|---|
| `Status` | `Open` | `Open`, `Reviewed`, `Cleared`, `Escalated` (dropdown in Excel) |
| `Notes` | *(blank)* | Free-text — manager types their notes here |

**Row color coding by Status:**
- **No fill** = Open
- **Light blue** = Reviewed
- **Light green** = Cleared
- **Light orange** = Escalated

Applies to: All Exceptions, Concession Audit (John), Revenue Integrity (Daniel), Fee Schedule Violations.  
All headers are dark blue with white bold text. Header row is frozen. Columns are auto-sized.

**Implemented in:** `export_to_excel()` → `_add_review_columns()` + `_format_flag_sheet()` in `audit_bot.py`.

---

## Critical Data Discoveries Made During Build

1. **Rent Roll column positions (positional CSV, no headers):**
   - col[0]=unit, col[2]=type, col[5]=residents, col[10]=status, col[12]=market_rent
   - col[18]=description, **col[21]=amount** (was wrong as 22), col[25]=move_in
   - col[26]=lease_start, col[27]=lease_end, **col[35]=balance** (was wrong as 36)

2. **Encoding:** All CSVs use cp1252/latin-1 (Windows-1252). `_read_csv()` tries utf-8-sig → cp1252 → latin-1.

3. **Rec_Conc = $0** for every lease row in New & Renewed Leases export. Not a bug — LiveNjoy stores concessions as discounted rent, not a separate field.

4. **Concession source:** 193 units have negative-amount concession rows on the Rent Roll. These are the "approved" amounts used for John's R5/R6/R7.

---

## Daniel's Confirmed Answers (March 4, 2026)

1. **90% threshold** — Confirmed correct, BUT only applies after 1 year of ownership or 1 year since a fee was introduced. When a property is newly acquired, fees are added on new leases/renewals over time. The 90% rule is correct for established fees.

2. **Variance tolerance** — **$1 is the cutoff** (not $10). Example: pest control should be $6, if $5 is posted → flag it. Exception: fees change over time (e.g., $5 until June 30, then $6 from July 1) — this is handled by the fee schedule, which should be updated monthly as fees change.

3. **Optional charges whitelist** — Confirmed: **Carport/Reserved Parking**, **Pet Fees**, and **Washer/Dryer** may be missing for many units (unit-specific add-ons). Do NOT flag these as "Missing Standard Charge." Only flag them if they exist at the wrong amount.

4. **Resolution workflow** — **Yes, confirmed March 4, 2026.** Status + Notes columns added to all flag sheets in Excel. Dropdown: Open / Reviewed / Cleared / Escalated. Row color coding by status. Already implemented.

---

## Pending — Still Waiting

**John — partially answered (March 10, 2026):**
1. Approved concession term tracker per unit (to enable "Incorrect Frequency Setup" rule) — **redirected to Daniel, no answer yet**
2. ✅ Credit description wordings — confirmed freeform, no standard rule → **R4 disabled**
3. $700 CRITICAL threshold — **no answer yet** (John said it may change; tiered risk levels discussed but not implemented yet)
4. ✅ Approved codes confirmed: CONR, CRTCO, EMPL, MCCR, RRFee only

**Daniel — all 4 questions answered ✅**
1. ✅ 90% threshold confirmed
2. ✅ $1 variance confirmed
3. ✅ Optional charge whitelist confirmed (parking, pet, W/D)
4. ✅ Resolution workflow confirmed — Status/Notes columns implemented

**La Prada fee sheet** ✅ — received and added March 11, 2026.

**March 2026 CSV files** ✅ — received from Daniel on March 11, 2026. All 42 files loaded and audit run complete.

**Transaction List naming** — March files use full property names (e.g. `Crossings at Irving Transaction List.csv`) instead of the Feb short-code format (`CAI Transaction List (Credits) - Feb 2026.csv`). Bot handles both via `derive_property()` keyword mapping. Old Feb transaction files were deleted.

**Bug fix (March 11, 2026)** — Fixed pandas index alignment error in `run_fee_schedule_check()`. Added `unit_grp = unit_grp.reset_index(drop=True)` inside the unit groupby loop (line ~1238 in audit_bot.py). This was triggered by the new data and would have crashed every future run.

---

## Next Run — May 2026

1. Drop 42 CSV files into their matching `data/` subfolders (replace April files)
2. Change `AUDIT_MONTH = "May 2026"` in `audit_bot.py`
3. Run: `.venv\Scripts\python.exe audit_bot.py`
4. Dashboard: `.venv\Scripts\streamlit.exe run app.py` → http://localhost:8501

**Both bugs are now fixed** — output is reliable. The April 30 run is the first clean output.

**File naming note:** March/April files used full names (e.g. `Crossings at Irving Transaction List.csv`). Bot handles both short-code and full-name formats automatically.

⚠️ Before next run — confirm with Daniel that Transaction List export is filtered to the audit month only (Mar 1–31), not full history. March run produced 3,676 John flags vs 198 in Feb, likely due to full history export.

---

## Ready to Build Next (no input needed)

1. **WST false positive suppression** — Western Station manager always puts $20 pet fee + $50 W/D on leases even when they don't apply. Adds noise to the flag list. Can add a property+category suppression rule.
2. **Fee schedule effective dates** — fees change over time (e.g., pest $5 until June 30, then $6 from July 1). Current schedule is static. Can add `effective_from` date ranges per fee entry.
3. **Month-over-month diff** — compare current run to last run's Excel output to show which flags are new vs. persistent.
4. **Dashboard Status filter** — filter the Streamlit tables to show only `Open` flags, hiding `Cleared` ones.
5. **R3 tiered risk levels** — John said $700 threshold may change. Proposed tiers: <$100 = MEDIUM, $100–$200 = HIGH, >$200 = CRITICAL. On hold until John confirms.

---

## How to Continue in a New Chat

Paste this entire file into the new chat with a message like:
> "Here is the full context of my LNJ Audit Bot project. Please read it and continue from where we left off."

Then state what you want to work on next.
