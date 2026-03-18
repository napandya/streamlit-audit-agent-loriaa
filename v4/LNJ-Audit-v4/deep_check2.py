"""
Targeted false-positive check — variance rule breakdown by category
"""
import glob
import pandas as pd

f = sorted(glob.glob("output/*.xlsx"))[-1]
print(f"File: {f}\n")
xl = pd.ExcelFile(f)
dan = xl.parse("Revenue Integrity (Daniel)")

# Break down Major + Minor variance by category
for rule in ["Major Charge Amount Variance", "Minor Charge Amount Variance"]:
    grp = dan[dan["Rule"] == rule]
    print(f"\n{'='*60}")
    print(f"{rule}  ({len(grp)} flags)")
    # Extract category from Detail string
    grp = grp.copy()
    grp["_cat"] = grp["Detail"].str.extract(r"^'([^']+)'")
    print(grp.groupby("_cat").size().sort_values(ascending=False).to_string())

# Check overlap: Daniel "Manual Posting Without Setup" vs John "Missing Addendum"
john = xl.parse("Concession Audit (John)")
ma   = set(zip(john[john["Rule"]=="Missing Addendum"]["Property"],
               john[john["Rule"]=="Missing Addendum"]["Unit"]))
mp   = dan[dan["Rule"]=="Manual Posting Without Setup"].copy()
mp["_overlap"] = list(zip(mp["Property"], mp["Unit"].astype(str)))
overlap = mp[mp["_overlap"].apply(lambda x: x in ma)]
print(f"\n{'='*60}")
print(f"Manual Posting Without Setup: {len(mp)} flags")
print(f"  Of those, already caught by John R5 Missing Addendum: {len(overlap)}")
print(f"  Net new (not in John): {len(mp) - len(overlap)}")
for _, row in (mp[~mp["_overlap"].apply(lambda x: x in ma)]).iterrows():
    print(f"  UNIQUE TO DANIEL: {row['Property']} Unit {row['Unit']} | {row['Resident']} | {row['Detail']}")
