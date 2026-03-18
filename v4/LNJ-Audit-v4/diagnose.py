import sys, pandas as pd
sys.path.insert(0, "D:/Loriaa Projects/March/LNJ-Audit-v4")
from audit_bot import run_full_audit
R = run_full_audit()
j = R["johns_flags"]
d = R["daniels_flags"]
print("\n=== JOHN FLAGS BY RULE ===")
if not j.empty:
    print(j.groupby(["Rule","Risk_Level"])["Amount_Impact"].agg(Count="count", Total="sum").to_string())
print("\n=== DANIEL FLAGS BY RULE ===")
if not d.empty:
    print(d.groupby(["Rule","Risk_Level"])["Amount_Impact"].agg(Count="count", Total="sum").to_string())
