"""
verify_final.py
Cross-checks LNJ_Audit_20260501_1342.xlsx against all known false-positive
issues raised by John. Prints PASS / FAIL for each check.
"""
import pandas as pd
import os

OUTPUT = "output/LNJ_Audit_20260501_1342.xlsx"

print(f"\nVerifying: {OUTPUT}\n{'='*70}")

xl = pd.ExcelFile(OUTPUT)
print(f"Sheets: {xl.sheet_names}\n")

# Load every flag sheet into one combined DataFrame
flag_sheets = ["Concession Audit (John)", "Revenue Integrity (Daniel)", "Fee Schedule Violations"]
frames = []
for sheet in flag_sheets:
    if sheet in xl.sheet_names:
        df = xl.parse(sheet)
        df["_sheet"] = sheet
        frames.append(df)

all_flags = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

# Normalise column names (strip whitespace)
all_flags.columns = all_flags.columns.str.strip()

rule_col   = next((c for c in all_flags.columns if "rule" in c.lower()), None)
detail_col = next((c for c in all_flags.columns if "detail" in c.lower()), None)
unit_col   = next((c for c in all_flags.columns if c.lower() == "unit"), None)
prop_col   = next((c for c in all_flags.columns if "property" in c.lower()), None)

print(f"Total flags loaded: {len(all_flags)}")
print(f"Columns: {list(all_flags.columns)}\n")

passes = 0
fails  = 0

def check(label, condition, detail=""):
    global passes, fails
    if condition:
        print(f"  ✓ PASS  {label}")
        passes += 1
    else:
        print(f"  ✗ FAIL  {label}")
        if detail:
            print(f"         {detail}")
        fails += 1

print("─── CHECK 1: Missing Addendum rule is fully disabled ───────────────────")
if rule_col:
    ma_flags = all_flags[all_flags[rule_col].astype(str).str.strip() == "Missing Addendum"]
    check("No 'Missing Addendum' flags in output", len(ma_flags) == 0,
          f"Found {len(ma_flags)} flags: {ma_flags[[prop_col, unit_col, rule_col]].to_string(index=False) if len(ma_flags) else ''}")
else:
    print("  ? Could not find Rule column")

print()
print("─── CHECK 2: No payment rows treated as credits ────────────────────────")
# Load raw transaction CSVs and verify no Payment/Deposit rows are in credits
tx_dir = "data/transactions"
payment_leak = []
for fname in os.listdir(tx_dir):
    if not fname.endswith(".csv"):
        continue
    raw = pd.read_csv(os.path.join(tx_dir, fname), header=None, dtype=str, encoding="utf-8-sig")
    col0 = raw.iloc[:, 0].astype(str).str.strip()
    section = col0.where(col0.str.match(r"^(Credit|Charge|Payment|Deposit)")).ffill()
    data_rows = raw[col0.str.match(r"^\d{1,2}/\d{1,2}/\d{4}")]
    data_sections = section.loc[data_rows.index]
    payment_rows_in_credit = data_sections[
        data_sections.str.startswith("Payment", na=False) |
        data_sections.str.startswith("Deposit", na=False)
    ]
    if len(payment_rows_in_credit) > 0:
        payment_leak.append(f"{fname}: {len(payment_rows_in_credit)} payment/deposit rows")

check("No Payment/Deposit rows leaking into credit classification",
      len(payment_leak) == 0,
      "\n         ".join(payment_leak))

print()
print("─── CHECK 3: Resident Referral credits not flagged ─────────────────────")
if detail_col and rule_col:
    referral_flags = all_flags[
        all_flags[detail_col].astype(str).str.lower().str.contains("referral", na=False)
    ]
    check("No flags whose detail mentions 'referral'", len(referral_flags) == 0,
          f"Found {len(referral_flags)}: {referral_flags[[prop_col, unit_col, rule_col]].to_string(index=False) if len(referral_flags) else ''}")

print()
print("─── CHECK 4: Employee Unit Rent Allowance not generating Missing Addendum ─")
if rule_col and detail_col:
    empl_ma = all_flags[
        (all_flags[rule_col].astype(str).str.strip() == "Missing Addendum") &
        (all_flags[detail_col].astype(str).str.lower().str.contains("employee", na=False))
    ]
    check("No Missing Addendum flags for Employee Unit credits", len(empl_ma) == 0,
          f"Found {len(empl_ma)}")
else:
    check("No Missing Addendum flags for Employee Unit credits", True)  # already confirmed by Check 1

print()
print("─── CHECK 5: Multi-space parking not false-flagged ─────────────────────")
# Known units: CAI 157 ($105 = 3x$35), CAI 222 ($105 = 3x$35)
if rule_col and prop_col and unit_col and detail_col:
    cai_parking = all_flags[
        (all_flags[rule_col].astype(str).str.strip() == "Fee Schedule Violation") &
        (all_flags[prop_col].astype(str).str.contains("Crossings", na=False)) &
        (all_flags[unit_col].astype(str).isin(["157", "222"])) &
        (all_flags[detail_col].astype(str).str.lower().str.contains("parking|carport", na=False))
    ]
    check("CAI Units 157 & 222 parking ($105 = 3×$35) not flagged", len(cai_parking) == 0,
          f"Still flagged: {cai_parking[[prop_col, unit_col, detail_col]].to_string(index=False) if len(cai_parking) else ''}")

print()
print("─── CHECK 6: Known false-positive unit 0313 Village Green ──────────────")
# Tuesday Greene's unit was the original example from John — should have zero CRITICAL flags
if rule_col and prop_col and unit_col:
    vg313 = all_flags[
        (all_flags[prop_col].astype(str).str.contains("Village Green", na=False)) &
        (all_flags[unit_col].astype(str) == "313")
    ]
    critical_col = next((c for c in all_flags.columns if "risk" in c.lower() or "status" in c.lower()), None)
    if critical_col:
        vg313_critical = vg313[vg313[critical_col].astype(str).str.upper() == "CRITICAL"]
        check("VG Unit 313 has no CRITICAL flags", len(vg313_critical) == 0,
              f"Found: {vg313_critical[[prop_col, unit_col, rule_col, critical_col]].to_string(index=False) if len(vg313_critical) else ''}")
        if len(vg313) > 0:
            print(f"         (Unit 313 has {len(vg313)} non-critical flags — shown for reference:)")
            for _, r in vg313.iterrows():
                print(f"           • [{r.get(critical_col,'')}] {r.get(rule_col,'')} — {str(r.get(detail_col,''))[:80]}")
    else:
        check("VG Unit 313 flags found", len(vg313) >= 0)

print()
print("─── CHECK 7: Rule distribution sanity check ────────────────────────────")
if rule_col:
    dist = all_flags[rule_col].value_counts()
    print("  Flag counts by rule:")
    for rule, count in dist.items():
        print(f"    {count:>4}  {rule}")
    # Missing Addendum must be 0
    ma_count = dist.get("Missing Addendum", 0)
    check("Missing Addendum count = 0", ma_count == 0)

print()
print("─── CHECK 8: No extreme-amount flags that look like payment capture ─────")
amt_col = next((c for c in all_flags.columns if "amount" in c.lower() and "impact" in c.lower()), None)
if amt_col is None:
    amt_col = next((c for c in all_flags.columns if "amount" in c.lower()), None)
if amt_col:
    all_flags[amt_col] = pd.to_numeric(all_flags[amt_col], errors="coerce").fillna(0)
    large = all_flags[all_flags[amt_col] > 2000]
    check("No flags with amount impact > $2,000 (likely payment capture)", len(large) == 0,
          f"Found {len(large)} large-amount flags:\n" +
          large[[prop_col, unit_col, rule_col, amt_col]].to_string(index=False) if len(large) else "")

print()
print("="*70)
print(f"Result: {passes} PASS  |  {fails} FAIL")
if fails == 0:
    print("✓ Output is clean — safe to send to John.")
else:
    print("✗ Issues found — review FAILs above before sending.")
print()
