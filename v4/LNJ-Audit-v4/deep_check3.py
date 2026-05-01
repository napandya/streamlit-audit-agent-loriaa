"""
Deep quality check of LNJ_Audit_20260430_1119.xlsx
Checks every flag rule for potential false positives by cross-referencing raw CSVs.
"""
import os, re
import pandas as pd
import numpy as np

BASE = r"d:\Github LNJ\streamlit-audit-agent-loriaa\v4\LNJ-Audit-v4"
EXCEL = os.path.join(BASE, "output", "LNJ_Audit_20260430_1119.xlsx")

# ── helpers ──────────────────────────────────────────────────────────────────
def cc(v):
    if pd.isna(v) or str(v).strip() in ("","nan","--"): return 0.0
    try: return float(re.sub(r'[\$,\s"]+','',str(v)))
    except: return 0.0

def cu(v):
    s = str(v).strip() if not pd.isna(v) else ""
    if not s or s.lower()=="nan": return "UNKNOWN"
    if " - " in s: s = s.split(" - ")[0].strip()
    return s.lstrip("0") or "0"

def read_csv(path, **kw):
    for enc in ("utf-8-sig","cp1252","latin-1"):
        try: return pd.read_csv(path, encoding=enc, **kw)
        except UnicodeDecodeError: continue
    raise ValueError(path)

SEP = "="*70

# ── load audit output ────────────────────────────────────────────────────────
xl = pd.ExcelFile(EXCEL)
flags = xl.parse("All Exceptions")
# strip Status/Notes columns that were prepended
if "Status" in flags.columns: flags = flags.drop(columns=["Status","Notes"], errors="ignore")
print(f"\nLoaded {len(flags)} flags from {os.path.basename(EXCEL)}")
print("Rules present:", flags["Rule"].value_counts().to_dict())

# ── load raw data ─────────────────────────────────────────────────────────────
print("\nLoading raw CSVs…")

# Transaction List (Credit rows only, post-fix)
tx_frames = []
for fn in os.listdir(os.path.join(BASE,"data","transactions")):
    if not fn.endswith(".csv"): continue
    df = read_csv(os.path.join(BASE,"data","transactions",fn), skiprows=6, dtype=str)
    df.columns = [str(c).strip() for c in df.columns]
    dc = df.iloc[:,0].astype(str).str.strip()
    df["_sec"] = dc.where(dc.str.match(r"^(Credit|Charge|Payment|Deposit)")).ffill()
    df = df[df["_sec"].str.startswith("Credit - ",na=False) &
            (df["_sec"] != "Credit - Renters Insurance Premium Credit") &
            df["Unit"].astype(str).str.strip().str.match(r"^\d+$")].copy()
    # derive property from filename
    prop = fn
    for kw,p in [("crossings","Crossings at Irving"),("irving","Crossings at Irving"),
                 ("highland","Highland Park"),("prada","La Prada"),
                 ("taylor","Parks on Taylor"),("valencia","Valencia Plaza"),
                 ("village","Village Green"),("western","Western Station")]:
        if kw in fn.lower(): prop = p; break
    df["_prop"] = prop
    df["_unit"] = df["Unit"].apply(cu)
    df["_amt"]  = df["Amount"].apply(cc)
    df["_rev"]  = df["_amt"] < 0
    df["_desc"] = df.get("Description", pd.Series(dtype=str)).fillna("").str.strip().str.lower()
    df["_sec_label"] = df["_sec"]
    tx_frames.append(df[["_prop","_unit","_amt","_rev","_desc","_sec_label"]])
tx = pd.concat(tx_frames, ignore_index=True)
print(f"  Transaction rows: {len(tx)}")
print("  Sections in tx data:", tx["_sec_label"].value_counts().to_dict())

# Rent Roll
rr_frames = []
for fn in os.listdir(os.path.join(BASE,"data","rent_rolls")):
    if not fn.endswith(".csv"): continue
    raw = read_csv(os.path.join(BASE,"data","rent_rolls",fn), skiprows=6, header=0, dtype=str)
    while len(raw.columns) < 37: raw[f"_p{len(raw.columns)}"] = np.nan
    prop = fn
    for kw,p in [("crossing","Crossings at Irving"),("highland","Highland Park"),
                 ("prada","La Prada"),("taylor","Parks on Taylor"),
                 ("valencia","Valencia Plaza"),("village","Village Green"),
                 ("western","Western Station")]:
        if kw in fn.lower(): prop = p; break
    cur_unit=cur_res=cur_status=cur_lease_end=None
    rows=[]
    for _,row in raw.iterrows():
        c0=str(row.iloc[0]).strip(); c10=str(row.iloc[10]).strip()
        c18=str(row.iloc[18]).strip(); c21=str(row.iloc[21]).strip()
        c27=str(row.iloc[27]).strip()
        if c18.lower()=="total": continue
        if re.match(r"^\d+$",c0):
            cur_unit=cu(c0)
            cur_res=re.sub(r"\*+","",str(row.iloc[5])).strip()
            cur_status=c10
            try: cur_lease_end=pd.to_datetime(c27,infer_datetime_format=True)
            except: cur_lease_end=None
            if c18 not in ("","nan"):
                rows.append({"prop":prop,"unit":cur_unit,"res":cur_res,"status":cur_status,
                             "desc":c18.lower(),"amt":cc(c21),"lease_end":cur_lease_end})
        elif cur_unit and c18 not in ("","nan"):
            rows.append({"prop":prop,"unit":cur_unit,"res":cur_res,"status":cur_status,
                         "desc":c18.lower(),"amt":cc(c21),"lease_end":cur_lease_end})
    rr_frames.append(pd.DataFrame(rows))
rr = pd.concat(rr_frames, ignore_index=True)
print(f"  Rent Roll rows: {len(rr)}")

# Projection
proj_frames = []
AUDIT_MONTH = "Apr 2026"
for fn in os.listdir(os.path.join(BASE,"data","recurring")):
    if not fn.endswith(".csv"): continue
    raw = read_csv(os.path.join(BASE,"data","recurring",fn), header=None, dtype=str)
    prop = fn
    for kw,p in [("crossing","Crossings at Irving"),("highland","Highland Park"),
                 ("prada","La Prada"),("taylor","Parks on Taylor"),
                 ("valencia","Valencia Plaza"),("village","Village Green"),
                 ("western","Western Station")]:
        if kw in fn.lower(): prop = p; break
    marker = raw[raw.iloc[:,0].astype(str).str.strip()=="Recurring Transactions by Unit"].index
    if marker.empty: continue
    sec = marker[0]+1; hdr = raw.iloc[sec]
    mcol=None
    for i,h in enumerate(hdr):
        if AUDIT_MONTH.lower() in str(h).lower(): mcol=i; break
    if mcol is None: mcol=3
    data = raw.iloc[sec+1:].copy()
    data.columns = range(len(data.columns))
    data = data[data[0].astype(str).str.strip().str.match(r"^\d")]
    for _,row in data.iterrows():
        raw_u=str(row[0]).strip()
        unit_num=cu(raw_u)
        cat=str(row[2]).strip() if pd.notna(row[2]) else ""
        amt=cc(row[mcol])
        proj_frames.append({"prop":prop,"unit":unit_num,"cat":cat.lower(),"amt":amt})
proj = pd.concat([pd.DataFrame(proj_frames)], ignore_index=True)
print(f"  Projection rows: {len(proj)}")

print(SEP)

# ════════════════════════════════════════════════════════════════════════════
# CHECK 1 — Missing Addendum: is every flagged TX row actually a concession?
# ════════════════════════════════════════════════════════════════════════════
print("\n[CHECK 1] Missing Addendum — verifying each flagged unit's TX row descriptions")
CONC_TX_KW = ["concession","allowance","employee unit","courtesy officer",
              "resident referral","referral","move in special","move-in special",
              "reduce","special","discount","conr","crtco","empl","mccr"]
ma_flags = flags[flags["Rule"]=="Missing Addendum"]
issues = []
clean = []
for _,row in ma_flags.iterrows():
    prop=row["Property"]; unit=str(row["Unit"])
    unit_tx = tx[(tx["_prop"]==prop) & (tx["_unit"]==unit) & (~tx["_rev"]) & (tx["_amt"]>0)]
    descs = unit_tx["_desc"].tolist()
    secs  = unit_tx["_sec_label"].unique().tolist()
    is_conc = any(any(k in d for k in CONC_TX_KW) for d in descs)
    is_insurance = all("insurance" in d or "renters" in d for d in descs) if descs else False
    if not descs:
        issues.append(f"  ⚠  {prop} Unit {unit} — flagged but NO active credit rows found in tx data at all!")
    elif not is_conc:
        issues.append(f"  ⚠  {prop} Unit {unit} — descriptions don't look like concessions: {descs[:3]}")
    elif is_insurance:
        issues.append(f"  ⚠  {prop} Unit {unit} — looks like insurance credit, not concession: {descs[:3]}")
    else:
        clean.append(f"  ✓  {prop} Unit {unit} — {descs[:2]}")
print(f"  Total Missing Addendum flags: {len(ma_flags)}")
print(f"  Confirmed concession-type: {len(clean)}")
print(f"  Suspicious / possible false positives: {len(issues)}")
if issues:
    for i in issues: print(i)

print(SEP)

# ════════════════════════════════════════════════════════════════════════════
# CHECK 2 — Recurring Concession >$700: verify against Transaction List sections
# ════════════════════════════════════════════════════════════════════════════
print("\n[CHECK 2] Recurring Concession >$700 — checking what section each comes from")
rc_flags = flags[flags["Rule"]=="Recurring Concession >$700"]
for _,row in rc_flags.iterrows():
    prop=row["Property"]; unit=str(row["Unit"]); amt=row["Amount_Impact"]
    unit_tx = tx[(tx["_prop"]==prop) & (tx["_unit"]==unit) & (~tx["_rev"])]
    secs  = unit_tx["_sec_label"].unique().tolist()
    descs = unit_tx["_desc"].unique().tolist()
    print(f"  {prop} Unit {unit} ${amt:.2f} | sections={secs} | descs={descs[:3]}")

print(SEP)

# ════════════════════════════════════════════════════════════════════════════
# CHECK 3 — Not Properly Posted: RR concession exists but no TX credit
#           Is the RR keyword match actually finding real concession rows?
# ════════════════════════════════════════════════════════════════════════════
print("\n[CHECK 3] Not Properly Posted — verifying RR concession rows are genuine")
CONC_RR_KW = ["concession","$999","special","reduce","employee","discount",
               "free","$200","$100","allowance","courtesy","mi special",
               "move in","move-in","rent concession"]
npp_flags = flags[flags["Rule"]=="Not Properly Posted"]
print(f"  Total Not Properly Posted flags: {len(npp_flags)}")
for _,row in npp_flags.iterrows():
    prop=row["Property"]; unit=str(row["Unit"])
    unit_rr = rr[(rr["prop"]==prop) & (rr["unit"]==unit) & (rr["amt"]<-0.01)]
    conc_rr = unit_rr[unit_rr["desc"].apply(lambda d: any(k in d for k in CONC_RR_KW))]
    non_conc = unit_rr[~unit_rr["desc"].apply(lambda d: any(k in d for k in CONC_RR_KW))]
    if non_conc.empty and not conc_rr.empty:
        print(f"  ✓  {prop} Unit {unit} — RR concession row: {conc_rr['desc'].tolist()} ${conc_rr['amt'].tolist()}")
    elif not non_conc.empty:
        print(f"  ⚠  {prop} Unit {unit} — negative RR row matched but desc may not be concession: {non_conc['desc'].tolist()}")
    else:
        print(f"  ??  {prop} Unit {unit} — no negative RR row found at all (detail: {row['Detail'][:80]})")

print(SEP)

# ════════════════════════════════════════════════════════════════════════════
# CHECK 4 — Concession Amount Mismatch: does TX credit desc look like concession?
# ════════════════════════════════════════════════════════════════════════════
print("\n[CHECK 4] Concession Amount Mismatch — spot check descriptions")
cam_flags = flags[flags["Rule"]=="Concession Amount Mismatch"]
print(f"  Total: {len(cam_flags)}")
issues=[]
for _,row in cam_flags.iterrows():
    prop=row["Property"]; unit=str(row["Unit"])
    unit_tx = tx[(tx["_prop"]==prop) & (tx["_unit"]==unit) & (~tx["_rev"]) & (tx["_amt"]>0)]
    descs = unit_tx["_desc"].tolist()
    is_conc = any(any(k in d for k in CONC_TX_KW) for d in descs)
    if not is_conc:
        issues.append(f"  ⚠  {prop} Unit {unit} TX desc not concession-like: {descs[:3]}")
print(f"  Confirmed concession: {len(cam_flags)-len(issues)}")
if issues:
    for i in issues: print(i)

print(SEP)

# ════════════════════════════════════════════════════════════════════════════
# CHECK 5 — Manual Posting Without Setup: TX credit but no projection row
#           Are the TX descriptions genuinely concession-like?
# ════════════════════════════════════════════════════════════════════════════
print("\n[CHECK 5] Manual Posting Without Setup — checking TX descriptions")
mp_flags = flags[flags["Rule"]=="Manual Posting Without Setup"]
print(f"  Total: {len(mp_flags)}")
issues=[]
for _,row in mp_flags.iterrows():
    prop=row["Property"]; unit=str(row["Unit"])
    unit_tx = tx[(tx["_prop"]==prop) & (tx["_unit"]==unit) & (~tx["_rev"]) & (tx["_amt"]>0)]
    descs = unit_tx["_desc"].tolist()
    secs  = unit_tx["_sec_label"].unique().tolist()
    is_conc = any(any(k in d for k in CONC_TX_KW) for d in descs)
    if not is_conc:
        issues.append(f"  ⚠  {prop} Unit {unit} — TX desc not concession: {descs[:3]} | sec={secs}")
    else:
        print(f"  ✓  {prop} Unit {unit} — {descs[:2]}")
if issues:
    print(f"\n  Suspicious ({len(issues)}):")
    for i in issues: print(i)

print(SEP)

# ════════════════════════════════════════════════════════════════════════════
# CHECK 6 — $0 Net Rent (Not Recent): verify units are truly occupied with $0
# ════════════════════════════════════════════════════════════════════════════
print("\n[CHECK 6] $0 Net Rent (Not Recent) — verifying unit is occupied and truly $0 rent")
zero_flags = flags[flags["Rule"]=="$0 Net Rent (Not Recent)"]
print(f"  Total: {len(zero_flags)}")
for _,row in zero_flags.iterrows():
    prop=row["Property"]; unit=str(row["Unit"])
    unit_rr = rr[(rr["prop"]==prop) & (rr["unit"]==unit)]
    rent_rows = unit_rr[unit_rr["desc"].str.contains(r"\brent\b|\bbase\b",na=False,regex=True) &
                        ~unit_rr["desc"].str.contains("concession",na=False)]
    net = rent_rows["amt"].sum()
    statuses = unit_rr["status"].unique().tolist()
    lease_ends = unit_rr["lease_end"].dropna().unique().tolist()
    print(f"  {prop} Unit {unit} | status={statuses} | rent rows sum=${net:.2f} | lease_end={[str(le.date()) if le else None for le in lease_ends]}")
    if rent_rows.empty:
        print(f"    ⚠  No rent rows found on RR — may be a data gap")

print(SEP)

# ════════════════════════════════════════════════════════════════════════════
# CHECK 7 — Posted vs Recurring Mismatch: are the deltas plausible?
#           Flag any case where recurring = 0 (setup missing entirely)
#           or where the mismatch > 100% of market rent (likely parsing error)
# ════════════════════════════════════════════════════════════════════════════
print("\n[CHECK 7] Posted vs Recurring Mismatch — checking for implausible deltas")
pvr_flags = flags[flags["Rule"]=="Posted vs Recurring Mismatch"].copy()
print(f"  Total: {len(pvr_flags)}")

# Extract numbers from detail string
def parse_pvr(detail):
    nums = re.findall(r'\$([\d,]+\.?\d*)', str(detail))
    if len(nums)>=2:
        return cc(nums[0]), cc(nums[1])
    return None, None

extremes = []
zero_rec = []
small_delta = []
for _,row in pvr_flags.iterrows():
    rec, posted = parse_pvr(row["Detail"])
    if rec is None: continue
    if rec == 0:
        zero_rec.append(f"  ⚠  ZERO REC: {row['Property']} Unit {row['Unit']} posted=${posted:.0f}")
    delta = abs(row["Amount_Impact"])
    if delta < 6:
        small_delta.append(f"  ℹ  tiny delta ${delta:.2f}: {row['Property']} Unit {row['Unit']}")
    if posted > 0 and rec > 0 and delta / max(posted,rec) > 2.0:
        extremes.append(f"  ⚠  extreme ratio {delta/max(posted,rec):.1f}x: {row['Property']} Unit {row['Unit']} rec=${rec:.0f} posted=${posted:.0f}")

print(f"  Zero-recurring-setup cases: {len(zero_rec)}")
for z in zero_rec[:10]: print(z)
print(f"  Tiny delta (<$6, possible rounding): {len(small_delta)}")
for s in small_delta[:5]: print(s)
print(f"  Extreme ratio mismatches (>2x): {len(extremes)}")
for e in extremes[:10]: print(e)

print(SEP)

# ════════════════════════════════════════════════════════════════════════════
# CHECK 8 — Missing Standard Charge: check the 90% rule is not firing on
#           newly acquired properties or optional-adjacent fees
# ════════════════════════════════════════════════════════════════════════════
print("\n[CHECK 8] Missing Standard Charge — checking for false positives")
msc_flags = flags[flags["Rule"]=="Missing Standard Charge"]
print(f"  Total: {len(msc_flags)}")
print("  By property:")
print(msc_flags.groupby("Property")["Unit"].count().to_string())
print("  Unique categories flagged:")
# extract category from detail
cats = msc_flags["Detail"].str.extract(r"'([^']+)'")[0].value_counts()
print(cats.to_string())

# Check if any optional-charge keyword crept in
OPTIONAL_KW = {"carport","parking","pet rent","pet fee","washer","dryer","first floor","1st floor"}
opt_leaks = msc_flags[msc_flags["Detail"].str.lower().apply(
    lambda d: any(k in d for k in OPTIONAL_KW)
)]
if not opt_leaks.empty:
    print(f"\n  ⚠  Optional-charge keywords found in MSC flags ({len(opt_leaks)} rows):")
    print(opt_leaks[["Property","Unit","Detail"]].to_string())
else:
    print("\n  ✓  No optional charges found in Missing Standard Charge flags")

print(SEP)

# ════════════════════════════════════════════════════════════════════════════
# CHECK 9 — Fee Schedule Violations: are any >$200 variance (likely wrong unit)?
# ════════════════════════════════════════════════════════════════════════════
print("\n[CHECK 9] Fee Schedule Violations — checking for outlier variances")
fsv_flags = flags[flags["Rule"]=="Fee Schedule Violation"]
print(f"  Total: {len(fsv_flags)}")
print(f"  Variance distribution:")
print(fsv_flags["Amount_Impact"].describe().round(2).to_string())
large_var = fsv_flags[fsv_flags["Amount_Impact"] > 50]
print(f"\n  Large variance (>$50) — {len(large_var)} flags:")
print(large_var[["Property","Unit","Resident","Detail","Amount_Impact"]].to_string())

print(SEP)

# ════════════════════════════════════════════════════════════════════════════
# CHECK 10 — Resident Referral credit section: are these valid concessions?
#            They appear in TX as "Credit - Resident Referral" — should NOT be
#            treated the same as "Credit - Concession - Rent"
# ════════════════════════════════════════════════════════════════════════════
print("\n[CHECK 10] Credit - Resident Referral rows — are these flagging correctly?")
referral_tx = tx[tx["_sec_label"]=="Credit - Resident Referral"]
print(f"  Resident Referral rows in TX data: {len(referral_tx)}")
if not referral_tx.empty:
    print(referral_tx[["_prop","_unit","_amt","_desc"]].to_string())
    # Are any of these units generating Missing Addendum flags?
    for _,row in referral_tx.iterrows():
        match = flags[(flags["Property"]==row["_prop"]) &
                      (flags["Unit"].astype(str)==row["_unit"]) &
                      (flags["Rule"]=="Missing Addendum")]
        if not match.empty:
            print(f"  ⚠  Referral credit for {row['_prop']} Unit {row['_unit']} is generating Missing Addendum flag!")

print(SEP)

# ════════════════════════════════════════════════════════════════════════════
# CHECK 11 — Employee Unit Rent Allowance: same question — valid concession?
# ════════════════════════════════════════════════════════════════════════════
print("\n[CHECK 11] Credit - Employee Unit Rent Allowance rows")
emp_tx = tx[tx["_sec_label"]=="Credit - Employee Unit Rent Allowance"]
print(f"  Employee Unit rows in TX data: {len(emp_tx)}")
if not emp_tx.empty:
    print(emp_tx[["_prop","_unit","_amt","_desc"]].head(10).to_string())
    for _,row in emp_tx.iterrows():
        match = flags[(flags["Property"]==row["_prop"]) &
                      (flags["Unit"].astype(str)==row["_unit"]) &
                      (flags["Rule"]=="Missing Addendum")]
        if not match.empty:
            print(f"  ⚠  Employee credit {row['_prop']} Unit {row['_unit']} generating Missing Addendum flag!")

print(SEP)
print("\n[DONE] Deep check complete.")
