"""
LiveNjoy ResMan Forensic Audit Engine
======================================
Authors: John B. (Concession Rules) + Daniel Twito (Revenue Integrity Rules)
Company: LiveNjoy Residential  |  System: ResMan

Implements:
  - John's 7 active concession rules (R4 disabled)  (run_johns_engine)
  - Daniel's 2-stage revenue integrity engine  (run_daniels_engine)
  - Fee schedule amount validation  (run_fee_schedule_check)
  - Manager override leaderboard  (run_manager_override_audit)
  - Financial exposure aggregation  (calculate_exposure)
  - Top-level orchestrator  (run_resman_audit)

All constants are imported from config.fee_schedules (not hardcoded here).
"""

from __future__ import annotations

import os
import re
from datetime import datetime

import numpy as np
import pandas as pd

from config.fee_schedules import (
    AUDIT_MONTH,
    CONCESSION_CRITICAL_AMT,
    CONCESSION_HIGH_AMT,
    OPTIONAL_CHARGE_KEYWORDS,
    PROPERTY_FEE_SCHEDULE,
    RECENT_MOVEIN_DAYS,
    RISK_CRITICAL,
    RISK_HIGH,
    RISK_MEDIUM,
    STANDARD_CHARGE_THRESHOLD,
)
from utils.csv_helpers import derive_property, read_csv_robust

# ---------------------------------------------------------------------------
# RISK MAP — rule name → risk level
# ---------------------------------------------------------------------------
RISK_MAP: dict[str, str] = {
    # John's Rules
    "Post-Term Credit": RISK_CRITICAL,
    "Recurring Concession >$700": RISK_CRITICAL,
    "Missing Addendum": RISK_CRITICAL,
    "Missing Lease": RISK_HIGH,
    "Concession Amount Mismatch": RISK_HIGH,
    "Not Properly Posted": RISK_HIGH,
    # Daniel's Stage 1
    "Missing Standard Charge": RISK_HIGH,
    "Major Charge Amount Variance": RISK_HIGH,
    "Concession >$500 for 2+ Months": RISK_HIGH,
    "Minor Charge Amount Variance": RISK_MEDIUM,
    "Concession No Expiration": RISK_MEDIUM,
    # Daniel's Stage 2
    "Negative Net Rent": RISK_CRITICAL,
    "$0 Net Rent (Not Recent)": RISK_CRITICAL,
    "Manual Posting Without Setup": RISK_HIGH,
    "Posted vs Recurring Mismatch": RISK_HIGH,
    "Misc Tenant Credit": RISK_HIGH,
    "$0 Net Rent (Recent Move-in)": RISK_MEDIUM,
    # Fee Schedule
    "Fee Schedule Violation": RISK_HIGH,
}

# Stage classification sets used by the UI
STAGE1_RULES = {
    "Missing Standard Charge",
    "Major Charge Amount Variance",
    "Minor Charge Amount Variance",
    "Recurring Concession >$700",
    "Concession >$500 for 2+ Months",
    "Concession No Expiration",
    "Post-Term Credit",
}
STAGE2_RULES = {
    "Negative Net Rent",
    "$0 Net Rent (Recent Move-in)",
    "$0 Net Rent (Not Recent)",
    "Manual Posting Without Setup",
    "Invalid Credit Code",
    "Posted vs Recurring Mismatch",
    "Misc Tenant Credit",
}


# ===========================================================================
# SECTION 1 — CLEANING HELPERS
# ===========================================================================

def _clean_currency(val) -> float:
    """Strip $, commas, spaces → float. Returns 0.0 on failure."""
    if pd.isna(val) or str(val).strip() in ("", "nan", "--"):
        return 0.0
    cleaned = re.sub(r'[$,"\s]', "", str(val))
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def _clean_unit(val) -> str:
    """Normalise unit number: strip leading zeros, handle '101 - Name' format."""
    s = str(val).strip() if not pd.isna(val) else ""
    if not s or s.lower() == "nan":
        return "UNKNOWN"
    if " - " in s:
        s = s.split(" - ")[0].strip()
    return s.lstrip("0") or "0"


def _parse_date(val):
    """Best-effort date parser; returns pd.Timestamp or None."""
    if pd.isna(val) or str(val).strip() in ("", "nan"):
        return None
    try:
        return pd.to_datetime(val, format="mixed", dayfirst=False)
    except Exception:
        return None


def _is_date_string(s: str) -> bool:
    """Return True if string looks like M/D/YYYY."""
    return bool(re.match(r"^\d{1,2}/\d{1,2}/\d{2,4}$", str(s).strip()))


def _derive_property(filename: str) -> str:
    """Map a ResMan export filename to the canonical full property name."""
    return derive_property(filename)


def _make_flag(
    property_name: str,
    unit: str,
    resident: str,
    rule: str,
    detail: str,
    amount_impact: float,
    source_file: str,
) -> dict:
    """Build a standardised exception record."""
    return {
        "Property": property_name,
        "Unit": unit,
        "Resident": resident,
        "Rule": rule,
        "Risk_Level": RISK_MAP.get(rule, RISK_MEDIUM),
        "Detail": detail,
        "Amount_Impact": round(float(amount_impact), 2),
        "Source_File": source_file,
    }


# ===========================================================================
# SECTION 2 — SPECIALISED LOADERS
# ===========================================================================

def _csv_files(folder: str) -> list[str]:
    if not os.path.exists(folder):
        return []
    return [f for f in os.listdir(folder) if f.lower().endswith(".csv")]


def _read_csv(fpath: str, **kwargs) -> pd.DataFrame:
    """Try utf-8-sig → cp1252 → latin-1 (Windows ResMan exports)."""
    return read_csv_robust(fpath, **kwargs)


def _load_transaction_list(folder: str) -> pd.DataFrame:
    all_data = []
    for fname in _csv_files(folder):
        fpath = os.path.join(folder, fname)
        try:
            df = _read_csv(fpath, skiprows=6, dtype=str)
            df.columns = [str(c).strip() for c in df.columns]
            df["_prop"] = _derive_property(fname)
            df["Source_File"] = fname

            df = df[df["Unit"].astype(str).str.strip().str.match(r"^\d+$")].copy()

            df["Property"] = df["_prop"]
            df["Unit"] = df["Unit"].apply(_clean_unit)
            df["Amount"] = df["Amount"].apply(_clean_currency)
            df["Is_Reversal"] = df["Amount"] < 0
            df["Description"] = df.get("Description", pd.Series(dtype=str)).fillna("").str.strip()
            df["Name"] = df.get("Name", pd.Series(dtype=str)).fillna("Unknown")
            df["Date"] = df.get("Date", pd.Series(dtype=str)).apply(_parse_date)

            rdate = df.columns[df.columns.str.strip() == "Reverse Date"]
            df["Reverse Date"] = df[rdate[0]] if len(rdate) else ""

            all_data.append(df)
        except Exception as exc:
            print(f"  [resman_rules] WARN transactions/{fname}: {exc}")

    return pd.concat(all_data, ignore_index=True) if all_data else pd.DataFrame()


def _load_leases(folder: str) -> pd.DataFrame:
    all_data = []
    for fname in _csv_files(folder):
        fpath = os.path.join(folder, fname)
        try:
            df = _read_csv(fpath, skiprows=5, dtype=str)
            df.columns = [str(c).strip() for c in df.columns]
            df["Property"] = _derive_property(fname)
            df["Source_File"] = fname

            df = df[df["Unit"].astype(str).str.strip().str.match(r"^\d+$")].copy()

            df["Unit"] = df["Unit"].apply(_clean_unit)
            df["Lease Start"] = df.get("Lease Start Date", pd.Series(dtype=str)).apply(_parse_date)
            df["Lease End"] = df.get("Lease End Date", pd.Series(dtype=str)).apply(_parse_date)
            df["Rec_Conc"] = df.get("Rec. Conc.", pd.Series(dtype=str)).apply(_clean_currency)
            df["One_Time_Conc"] = df.get("One Time Conc.", pd.Series(dtype=str)).apply(_clean_currency)
            df["Rent"] = df.get("Rent", pd.Series(dtype=str)).apply(_clean_currency)
            df["Market_Rent"] = df.get("Market Rent", pd.Series(dtype=str)).apply(_clean_currency)
            df["Residents"] = df.get("Residents", pd.Series(dtype=str)).fillna("Unknown")

            all_data.append(df)
        except Exception as exc:
            print(f"  [resman_rules] WARN leases/{fname}: {exc}")

    return pd.concat(all_data, ignore_index=True) if all_data else pd.DataFrame()


def _load_edits(folder: str) -> pd.DataFrame:
    all_data = []
    for fname in _csv_files(folder):
        fpath = os.path.join(folder, fname)
        try:
            df = _read_csv(fpath, skiprows=5, dtype=str, header=0)
            df.columns = [str(c).strip() for c in df.columns]
            prop = _derive_property(fname)

            current_manager = "Unknown"
            records = []

            for _, row in df.iterrows():
                val = str(row.iloc[0]).strip()
                if val in ("nan", ""):
                    continue

                if _is_date_string(val):
                    unit = _clean_unit(row.get("Unit", ""))
                    orig_amt = _clean_currency(row.get("Amount", 0))
                    rev_date = str(row.get("Reversal Date", "")).strip()
                    edited_raw = str(row.get("Edited Amount", "")).strip()
                    edited_amt = _clean_currency(edited_raw) if edited_raw not in ("", "nan") else None

                    is_reversal = rev_date not in ("", "nan")
                    is_amt_change = edited_amt is not None and abs(edited_amt - orig_amt) > 0.01

                    if not is_reversal and not is_amt_change:
                        continue

                    revenue_impact = -orig_amt if is_reversal else (edited_amt - orig_amt)
                    event_type = "Reversal" if is_reversal else "Amount Change"

                    records.append({
                        "Property": prop,
                        "Manager_Login": current_manager,
                        "Unit": unit,
                        "Resident": str(row.get("Name", "Unknown")),
                        "Category": str(row.get("Category", "Unknown")),
                        "Description": str(row.get("Description", "")),
                        "Original_Amount": orig_amt,
                        "Edited_Amount": edited_amt if edited_amt is not None else orig_amt,
                        "Event_Type": event_type,
                        "Revenue_Impact": revenue_impact,
                        "Date": _parse_date(val),
                        "Source_File": fname,
                    })
                else:
                    if not val.startswith("Date"):
                        current_manager = val

            if records:
                all_data.append(pd.DataFrame(records))
        except Exception as exc:
            print(f"  [resman_rules] WARN edits/{fname}: {exc}")

    return pd.concat(all_data, ignore_index=True) if all_data else pd.DataFrame()


def _load_transaction_projection(folder: str, audit_month: str = AUDIT_MONTH) -> pd.DataFrame:
    all_data = []
    for fname in _csv_files(folder):
        fpath = os.path.join(folder, fname)
        try:
            raw = _read_csv(fpath, header=None, dtype=str)
            prop = _derive_property(fname)

            marker_rows = raw[
                raw.iloc[:, 0].astype(str).str.strip() == "Recurring Transactions by Unit"
            ].index

            if marker_rows.empty:
                continue

            section_start = marker_rows[0] + 1
            header_row = raw.iloc[section_start]

            month_col_idx = None
            for i, h in enumerate(header_row):
                if audit_month.lower() in str(h).lower():
                    month_col_idx = i
                    break
            if month_col_idx is None:
                month_col_idx = 3

            data = raw.iloc[section_start + 1:].copy()
            data.columns = range(len(data.columns))
            data = data[data[0].astype(str).str.strip().str.match(r"^\d")]

            records = []
            for _, row in data.iterrows():
                raw_unit = str(row[0]).strip()
                unit_num = _clean_unit(raw_unit)
                resident = raw_unit.split(" - ", 1)[1].strip() if " - " in raw_unit else "Unknown"
                unit_type = str(row[1]).strip() if pd.notna(row[1]) else ""
                category = str(row[2]).strip() if pd.notna(row[2]) else ""
                amount = _clean_currency(row[month_col_idx])

                records.append({
                    "Property": prop,
                    "Unit": unit_num,
                    "Resident": resident,
                    "Unit_Type": unit_type,
                    "Category": category,
                    "Amount": amount,
                    "Source_File": fname,
                })

            if records:
                all_data.append(pd.DataFrame(records))
        except Exception as exc:
            print(f"  [resman_rules] WARN recurring/{fname}: {exc}")

    return pd.concat(all_data, ignore_index=True) if all_data else pd.DataFrame()


def _load_rent_roll(folder: str) -> pd.DataFrame:
    all_data = []
    for fname in _csv_files(folder):
        fpath = os.path.join(folder, fname)
        try:
            raw = _read_csv(fpath, skiprows=6, header=0, dtype=str)
            prop = _derive_property(fname)

            while len(raw.columns) < 37:
                raw[f"_pad_{len(raw.columns)}"] = np.nan

            current_unit = None
            current_resident = None
            current_type = None
            current_status = None
            current_mkt_rent = 0.0
            current_move_in = None
            current_lease_start = None
            current_lease_end = None
            current_balance = 0.0

            records = []

            for _, row in raw.iterrows():
                c0 = str(row.iloc[0]).strip()
                c2 = str(row.iloc[2]).strip()
                c5 = str(row.iloc[5]).strip()
                c10 = str(row.iloc[10]).strip()
                c12 = str(row.iloc[12]).strip()
                c18 = str(row.iloc[18]).strip()
                c21 = str(row.iloc[21]).strip()
                c25 = str(row.iloc[25]).strip()
                c26 = str(row.iloc[26]).strip()
                c27 = str(row.iloc[27]).strip()
                c35 = str(row.iloc[35]).strip() if len(row) > 35 else ""

                if c18.lower() == "total":
                    continue

                if re.match(r"^\d+$", c0):
                    current_unit = _clean_unit(c0)
                    current_resident = c5 if c5 not in ("", "nan") else "Unknown"
                    current_type = c2
                    current_status = c10
                    current_mkt_rent = _clean_currency(c12)
                    current_move_in = _parse_date(c25)
                    current_lease_start = _parse_date(c26)
                    current_lease_end = _parse_date(c27)
                    current_balance = _clean_currency(c35)

                    if c18 not in ("", "nan"):
                        records.append({
                            "Property": prop,
                            "Unit": current_unit,
                            "Residents": current_resident,
                            "Unit_Type": current_type,
                            "Status": current_status,
                            "Market_Rent": current_mkt_rent,
                            "Description": c18,
                            "Amount": _clean_currency(c21),
                            "Move_In": current_move_in,
                            "Lease_Start": current_lease_start,
                            "Lease_End": current_lease_end,
                            "Balance": current_balance,
                            "Source_File": fname,
                        })

                elif current_unit and c18 not in ("", "nan"):
                    records.append({
                        "Property": prop,
                        "Unit": current_unit,
                        "Residents": current_resident,
                        "Unit_Type": current_type,
                        "Status": current_status,
                        "Market_Rent": current_mkt_rent,
                        "Description": c18,
                        "Amount": _clean_currency(c21),
                        "Move_In": current_move_in,
                        "Lease_Start": current_lease_start,
                        "Lease_End": current_lease_end,
                        "Balance": current_balance,
                        "Source_File": fname,
                    })

            if records:
                all_data.append(pd.DataFrame(records))
        except Exception as exc:
            print(f"  [resman_rules] WARN rent_rolls/{fname}: {exc}")

    return pd.concat(all_data, ignore_index=True) if all_data else pd.DataFrame()


def _load_resident_activity(folder: str) -> pd.DataFrame:
    all_data = []
    for fname in _csv_files(folder):
        fpath = os.path.join(folder, fname)
        try:
            raw = _read_csv(fpath, skiprows=6, header=0, dtype=str)
            prop = _derive_property(fname)

            raw = raw[~raw.iloc[:, 0].astype(str).str.contains("Adjusted", na=False)]
            raw = raw[raw.iloc[:, 0].astype(str).str.strip().str.match(r"^\d+$")]

            while len(raw.columns) < 50:
                raw[f"_pad_{len(raw.columns)}"] = np.nan

            records = []
            for _, row in raw.iterrows():
                unit = _clean_unit(str(row.iloc[0]))
                residents = str(row.iloc[2]).strip()
                unit_type = str(row.iloc[18]).strip() if len(row) > 18 else ""
                actual_rent = _clean_currency(row.iloc[23]) if len(row) > 23 else 0.0
                move_in = _parse_date(row.iloc[29]) if len(row) > 29 else None
                lease_start = _parse_date(row.iloc[37]) if len(row) > 37 else None
                lease_end = _parse_date(row.iloc[43]) if len(row) > 43 else None

                manager = "Unknown"
                for i in range(len(row) - 1, 43, -1):
                    v = str(row.iloc[i]).strip()
                    if v not in ("", "nan"):
                        manager = v
                        break

                records.append({
                    "Property": prop,
                    "Unit": unit,
                    "Residents": residents,
                    "Unit_Type": unit_type,
                    "Actual_Rent": actual_rent,
                    "Move_In": move_in,
                    "Lease_Start": lease_start,
                    "Lease_End": lease_end,
                    "Manager": manager,
                    "Source_File": fname,
                })

            if records:
                all_data.append(pd.DataFrame(records))
        except Exception as exc:
            print(f"  [resman_rules] WARN activity/{fname}: {exc}")

    return pd.concat(all_data, ignore_index=True) if all_data else pd.DataFrame()


# ===========================================================================
# SECTION 3 — JOHN'S ENGINE (9 Concession Rules)
# ===========================================================================

def run_johns_engine(
    df_trans: pd.DataFrame,
    df_leases: pd.DataFrame,
    df_projection: pd.DataFrame | None = None,
    df_rent_roll: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """
    John's concession audit rules — 7 active rules (R4 disabled).

    R1  Post-Term Credit        — credit posted after lease end date (CRITICAL)
    R2  Missing Lease           — credit with no lease on file (HIGH)
    R3  Large Credit ≥$700      — single credit ≥ $700 (CRITICAL)
    R4  Non-Standard Description— DISABLED (March 10, 2026 per John)
    R5  Missing Addendum        — credit posted but no concession row on Rent Roll (CRITICAL)
    R6  Amount Mismatch         — Rent Roll concession ≠ Transaction List amount (HIGH)
    R7  Not Properly Posted     — Rent Roll has concession setup but no credit posted (HIGH)
    """
    flags = []

    if df_trans is None or df_trans.empty:
        return pd.DataFrame()

    CONC_RR_KW = [
        "concession", "$999", "special", "reduce", "employee", "discount",
        "free", "$200", "$100", "concession rent", "allowance", "courtesy",
        "mi special", "move in", "move-in", "rent concession",
    ]

    # Lease lookup: (prop, unit) → most-recent lease row
    lease_lookup: dict = {}
    if df_leases is not None and not df_leases.empty:
        for _, row in df_leases.sort_values("Lease Start", ascending=False).iterrows():
            key = (row["Property"], row["Unit"])
            if key not in lease_lookup:
                lease_lookup[key] = row

    # Rent Roll concession lookup: (prop, unit) → abs(sum of concession amounts)
    rr_conc_lookup: dict = {}
    rr_src_lookup: dict = {}
    if df_rent_roll is not None and not df_rent_roll.empty:
        conc_mask = (
            df_rent_roll["Description"].str.lower().apply(
                lambda x: any(k in x for k in CONC_RR_KW)
            )
            & (df_rent_roll["Amount"] < -0.01)
        )
        rr_conc_rows = df_rent_roll[conc_mask]
        for (prop, unit), grp in rr_conc_rows.groupby(["Property", "Unit"]):
            rr_conc_lookup[(prop, unit)] = abs(grp["Amount"].sum())
            rr_src_lookup[(prop, unit)] = grp["Source_File"].iloc[0]

    # Transaction List credit lookup: (prop, unit) → total active credits
    tx_credit_lookup: dict = {}
    tx_src_lookup: dict = {}
    tx_res_lookup: dict = {}
    active = df_trans[~df_trans["Is_Reversal"] & (df_trans["Amount"] > 0)]
    for (prop, unit), grp in active.groupby(["Property", "Unit"]):
        tx_credit_lookup[(prop, unit)] = grp["Amount"].sum()
        tx_src_lookup[(prop, unit)] = grp["Source_File"].iloc[0]
        tx_res_lookup[(prop, unit)] = grp["Name"].iloc[0]

    rr_market_lookup: dict = {}
    if df_rent_roll is not None and not df_rent_roll.empty:
        for (prop, unit), grp in df_rent_roll.groupby(["Property", "Unit"]):
            rr_market_lookup[(prop, unit)] = grp["Market_Rent"].iloc[0]

    # ------------------------------------------------------------------
    # R1, R2, R3 — per transaction-list unit
    # ------------------------------------------------------------------
    for (prop, unit), grp in df_trans.groupby(["Property", "Unit"]):
        resident = grp["Name"].iloc[0]
        src = grp["Source_File"].iloc[0]
        lease_row = lease_lookup.get((prop, unit))
        lease_end = lease_row.get("Lease End") if lease_row is not None else None

        active_credits = grp[~grp["Is_Reversal"] & (grp["Amount"] > 0)]
        net_actual = grp["Amount"].sum()

        # R1 — Post-Term Credit
        if lease_end is not None and pd.notna(lease_end):
            post_term = active_credits[
                active_credits["Date"].notna()
                & (active_credits["Date"] > pd.Timestamp(lease_end))
            ]
            for _, row in post_term.iterrows():
                flags.append(
                    _make_flag(
                        prop, unit, resident, "Post-Term Credit",
                        f"${row['Amount']:.2f} credit posted on "
                        f"{row['Date'].date()} after lease end "
                        f"{pd.Timestamp(lease_end).date()}. "
                        f"Description: '{row['Description']}'.",
                        row["Amount"], src,
                    )
                )

        # R2 — Missing Lease
        if net_actual > 0 and lease_row is None:
            flags.append(
                _make_flag(
                    prop, unit, resident, "Missing Lease",
                    f"${net_actual:.2f} net credit posted but no lease record "
                    f"found for Unit {unit} at {prop}.",
                    net_actual, src,
                )
            )

        # R3 — Large Credit ≥ $700
        for _, row in active_credits[
            active_credits["Amount"] >= CONCESSION_CRITICAL_AMT
        ].iterrows():
            flags.append(
                _make_flag(
                    prop, unit, resident, "Recurring Concession >$700",
                    f"Single credit of ${row['Amount']:.2f} exceeds "
                    f"${CONCESSION_CRITICAL_AMT} threshold. "
                    f"Description: '{row['Description']}'. Requires VP approval.",
                    row["Amount"], src,
                )
            )

    # ------------------------------------------------------------------
    # R5, R6, R7 — cross-check Rent Roll vs Transaction List
    # ------------------------------------------------------------------
    all_keys = set(list(rr_conc_lookup.keys()) + list(tx_credit_lookup.keys()))

    for (prop, unit) in all_keys:
        in_rr = (prop, unit) in rr_conc_lookup
        in_tx = (prop, unit) in tx_credit_lookup

        approved_amt = rr_conc_lookup.get((prop, unit), 0.0)
        posted_amt = tx_credit_lookup.get((prop, unit), 0.0)
        src = tx_src_lookup.get((prop, unit), rr_src_lookup.get((prop, unit), ""))
        market = rr_market_lookup.get((prop, unit), 0.0)

        resident = tx_res_lookup.get((prop, unit), "Unknown")
        if resident == "Unknown" and df_rent_roll is not None and not df_rent_roll.empty:
            rr_sub = df_rent_roll[
                (df_rent_roll["Property"] == prop) & (df_rent_roll["Unit"] == unit)
            ]
            if not rr_sub.empty:
                resident = rr_sub["Residents"].iloc[0]

        # R5 — Missing Addendum
        if in_tx and not in_rr:
            flags.append(
                _make_flag(
                    prop, unit, resident, "Missing Addendum",
                    f"${posted_amt:.2f} credit posted to Transaction List but "
                    f"unit has NO concession row on the Rent Roll. "
                    f"No lease addendum evident. (Market rent: ${market:.2f})",
                    posted_amt, src,
                )
            )

        # R6 — Amount Mismatch
        elif in_tx and in_rr:
            delta = abs(posted_amt - approved_amt)
            pct_diff = delta / approved_amt if approved_amt > 0 else 0
            if delta > 10 and pct_diff > 0.10:
                flags.append(
                    _make_flag(
                        prop, unit, resident, "Concession Amount Mismatch",
                        f"Rent Roll approves ${approved_amt:.2f}/mo but "
                        f"${posted_amt:.2f} was posted to Transaction List. "
                        f"Difference: ${delta:.2f} ({pct_diff * 100:.0f}%).",
                        delta, src,
                    )
                )

        # R7 — Not Properly Posted
        elif in_rr and not in_tx:
            flags.append(
                _make_flag(
                    prop, unit, resident, "Not Properly Posted",
                    f"${approved_amt:.2f} concession set up on Rent Roll "
                    f"but no credit posted to Transaction List for {AUDIT_MONTH}.",
                    approved_amt, src,
                )
            )

    return pd.DataFrame(flags) if flags else pd.DataFrame()


# ===========================================================================
# SECTION 4 — DANIEL'S ENGINE (2-Stage Revenue Integrity)
# ===========================================================================

def run_daniels_engine(
    df_projection: pd.DataFrame,
    df_rent_roll: pd.DataFrame,
    df_trans: pd.DataFrame,
    df_leases: pd.DataFrame,
    df_activity: pd.DataFrame,
) -> pd.DataFrame:
    """
    Stage 1 — Recurring Projection Audit
    Stage 2 — Posted Rent Roll Audit
    """
    flags = []

    # =========================================================================
    # STAGE 1 — RECURRING PROJECTION
    # =========================================================================
    if df_projection is not None and not df_projection.empty:
        proj = df_projection.copy()
        proj["Cat_Lower"] = proj["Category"].str.lower()

        # 3.1 — 90% RULE: standard charge missing from a unit
        for prop, prop_grp in proj.groupby("Property"):
            total_units = prop_grp["Unit"].nunique()
            if total_units == 0:
                continue

            for category, cat_grp in prop_grp.groupby("Category"):
                if not category:
                    continue
                if any(kw in category.lower() for kw in OPTIONAL_CHARGE_KEYWORDS):
                    continue

                units_with = cat_grp[cat_grp["Amount"] > 0]["Unit"].nunique()
                pct = units_with / total_units

                if pct >= STANDARD_CHARGE_THRESHOLD:
                    all_units = set(prop_grp["Unit"].unique())
                    have_units = set(cat_grp[cat_grp["Amount"] > 0]["Unit"].unique())
                    missing = all_units - have_units

                    std_amount = cat_grp[cat_grp["Amount"] > 0]["Amount"].mode()
                    std_amount = std_amount.iloc[0] if not std_amount.empty else 0.0

                    for mu in missing:
                        sub = prop_grp[prop_grp["Unit"] == mu]
                        resident = sub["Resident"].iloc[0] if not sub.empty else "Unknown"
                        src = sub["Source_File"].iloc[0] if not sub.empty else ""
                        flags.append(
                            _make_flag(
                                prop, mu, resident, "Missing Standard Charge",
                                f"'{category}' is standard at {prop} "
                                f"({pct * 100:.0f}% of units, ${std_amount:.2f}/mo). "
                                f"Unit {mu} has no charge set.",
                                std_amount, src,
                            )
                        )

        # 3.2 — AMOUNT CONSISTENCY within Property + Unit_Type + Category
        for (prop, unit_type, category), grp in proj.groupby(["Property", "Unit_Type", "Category"]):
            if not category or not unit_type:
                continue
            active = grp[grp["Amount"] > 0]
            if len(active) < 3:
                continue
            mode_val = active["Amount"].mode()
            if mode_val.empty or mode_val.iloc[0] == 0:
                continue
            mode_amt = mode_val.iloc[0]

            for _, row in active.iterrows():
                var = abs(row["Amount"] - mode_amt)
                pct_var = var / mode_amt
                if var >= 1.0:
                    rule = (
                        "Major Charge Amount Variance"
                        if (pct_var >= 0.20 and var >= 5.0)
                        else "Minor Charge Amount Variance"
                    )
                    flags.append(
                        _make_flag(
                            prop, row["Unit"], row["Resident"], rule,
                            f"'{category}' ({unit_type}): Unit ${row['Amount']:.2f} vs "
                            f"standard ${mode_amt:.2f} (Delta ${var:.2f}, {pct_var * 100:.0f}%)",
                            var, row.get("Source_File", ""),
                        )
                    )

        # 3.3 — RECURRING CONCESSION RED FLAGS
        conc_kw = [
            "concession", "conr", "crtco", "empl", "mccr", "rrfee",
            "employee unit", "resident referral", "courtesy officer",
        ]
        conc_mask = proj["Cat_Lower"].apply(lambda x: any(k in x for k in conc_kw))
        conc_proj = proj[conc_mask].copy()

        if not conc_proj.empty:
            for (prop, unit), grp in conc_proj.groupby(["Property", "Unit"]):
                amt = grp["Amount"].max()
                months = (grp["Amount"] > 0).sum()
                resident = grp["Resident"].iloc[0]
                src = grp["Source_File"].iloc[0]

                if amt > CONCESSION_CRITICAL_AMT or abs(amt - 500) < 1.0:
                    flags.append(
                        _make_flag(
                            prop, unit, resident, "Recurring Concession >$700",
                            f"Recurring concession ${amt:.2f}/mo exceeds threshold.",
                            amt, src,
                        )
                    )

                if months > 2 and amt > CONCESSION_HIGH_AMT:
                    flags.append(
                        _make_flag(
                            prop, unit, resident, "Concession >$500 for 2+ Months",
                            f"${amt:.2f}/mo for {months} months (>2 months above "
                            f"${CONCESSION_HIGH_AMT}).",
                            amt * months, src,
                        )
                    )

    # =========================================================================
    # STAGE 2 — POSTED RENT ROLL
    # =========================================================================
    if df_rent_roll is not None and not df_rent_roll.empty:
        rr = df_rent_roll.copy()
        rr = rr[rr["Status"].isin(["C", "MTM", "NTV"])]

        movein_lookup: dict = {}
        if df_activity is not None and not df_activity.empty:
            for _, row in df_activity.iterrows():
                key = (row["Property"], row["Unit"])
                if key not in movein_lookup and row["Move_In"] is not None:
                    movein_lookup[key] = row["Move_In"]
        if df_leases is not None and not df_leases.empty:
            for _, row in df_leases.iterrows():
                key = (row["Property"], row["Unit"])
                if key not in movein_lookup:
                    mi = row.get("Lease Start")
                    if mi is not None and pd.notna(mi):
                        movein_lookup[key] = mi

        # 4.1 — NET RENT INTEGRITY
        for (prop, unit), grp in rr.groupby(["Property", "Unit"]):
            resident = grp["Residents"].iloc[0]
            src = grp["Source_File"].iloc[0]

            rent_rows = grp[
                grp["Description"].str.lower().str.contains(
                    r"\brent\b|\bbase\b", na=False, regex=True
                )
                & ~grp["Description"].str.lower().str.contains(r"concession", na=False)
            ]
            net_rent = rent_rows["Amount"].sum()

            if net_rent < 0:
                flags.append(
                    _make_flag(
                        prop, unit, resident, "Negative Net Rent",
                        f"Net rent ${net_rent:.2f} — concession exceeds rent.",
                        abs(net_rent), src,
                    )
                )
            elif net_rent == 0:
                move_in = movein_lookup.get((prop, unit))
                today = pd.Timestamp.today()
                if (
                    move_in is not None
                    and pd.notna(move_in)
                    and (today - pd.Timestamp(move_in)).days <= RECENT_MOVEIN_DAYS
                ):
                    flags.append(
                        _make_flag(
                            prop, unit, resident, "$0 Net Rent (Recent Move-in)",
                            f"Net rent $0 — moved in {pd.Timestamp(move_in).date()}, "
                            f"within {RECENT_MOVEIN_DAYS} days.",
                            0.0, src,
                        )
                    )
                else:
                    flags.append(
                        _make_flag(
                            prop, unit, resident, "$0 Net Rent (Not Recent)",
                            "Net rent is $0 and resident is not a recent move-in.",
                            0.0, src,
                        )
                    )

        # 4.2 — MANUAL CONCESSION (credit in TX but no projection setup)
        if df_trans is not None and not df_trans.empty and df_projection is not None and not df_projection.empty:
            proj_units = set(zip(df_projection["Property"], df_projection["Unit"]))
            active_credits = df_trans[(~df_trans["Is_Reversal"]) & (df_trans["Amount"] > 0)]
            unit_net = active_credits.groupby(["Property", "Unit"])["Amount"].sum()

            for (prop, unit), net in unit_net.items():
                if (prop, unit) not in proj_units and net > 0:
                    sub = active_credits[
                        (active_credits["Property"] == prop)
                        & (active_credits["Unit"] == unit)
                    ]
                    resident = sub["Name"].iloc[0] if not sub.empty else "Unknown"
                    src = sub["Source_File"].iloc[0] if not sub.empty else ""
                    flags.append(
                        _make_flag(
                            prop, unit, resident, "Manual Posting Without Setup",
                            f"${net:.2f} credit in Transaction List but no recurring "
                            f"concession in Projection for this unit.",
                            net, src,
                        )
                    )

        # 4.3 — POSTED vs RECURRING MISMATCH
        if df_projection is not None and not df_projection.empty:
            for (prop, unit), grp in rr.groupby(["Property", "Unit"]):
                rent_rows = grp[
                    grp["Description"].str.lower().str.contains(
                        r"\brent\b|\bbase\b", na=False, regex=True
                    )
                ]
                posted_rent = rent_rows["Amount"].sum()

                proj_sub = df_projection[
                    (df_projection["Property"] == prop)
                    & (df_projection["Unit"] == unit)
                    & df_projection["Category"].str.lower().str.contains(
                        r"\brent\b|\bbase\b", na=False, regex=True
                    )
                ]
                recurring_rent = proj_sub["Amount"].sum()

                if recurring_rent > 0 and posted_rent > 0:
                    var = recurring_rent - posted_rent
                    if abs(var) > 5.0:
                        resident = grp["Residents"].iloc[0]
                        src = grp["Source_File"].iloc[0]
                        flags.append(
                            _make_flag(
                                prop, unit, resident, "Posted vs Recurring Mismatch",
                                f"Recurring setup ${recurring_rent:.2f} vs "
                                f"Rent Roll ${posted_rent:.2f} (Delta ${var:.2f})",
                                abs(var), src,
                            )
                        )

        # 4.4 — MISC TENANT CREDIT REVIEW
        if df_trans is not None and not df_trans.empty:
            misc_kw = [
                "misc", "miscellaneous", "adjustment", "write-off",
                "write off", "reclass", "mccr",
            ]
            misc_mask = (
                df_trans["Description"].str.lower().apply(
                    lambda x: any(k in x for k in misc_kw)
                )
                & (~df_trans["Is_Reversal"])
                & (df_trans["Amount"] > 0)
            )
            for _, row in df_trans[misc_mask].iterrows():
                flags.append(
                    _make_flag(
                        row.get("Property", "?"),
                        row["Unit"],
                        str(row.get("Name", "Unknown")),
                        "Misc Tenant Credit",
                        f"Misc credit ${row['Amount']:.2f} — "
                        f"'{row['Description']}'. Review per Daniel's specification.",
                        row["Amount"],
                        row.get("Source_File", ""),
                    )
                )

    return pd.DataFrame(flags) if flags else pd.DataFrame()


# ===========================================================================
# SECTION 5 — FEE SCHEDULE CHECK
# ===========================================================================

def run_fee_schedule_check(df_projection: pd.DataFrame) -> pd.DataFrame:
    """
    Validate each unit's recurring charges against PROPERTY_FEE_SCHEDULE.

    Per Daniel Twito: $1 is the variance cutoff.
    Only flags units where a charge EXISTS but has the WRONG amount.
    Missing charges are handled by the 90% Missing Standard Charge rule.
    """
    flags = []

    if df_projection is None or df_projection.empty:
        return pd.DataFrame()

    for prop, prop_grp in df_projection.groupby("Property"):
        schedule = PROPERTY_FEE_SCHEDULE.get(prop)
        if not schedule:
            continue

        for unit, unit_grp in prop_grp.groupby("Unit"):
            unit_grp = unit_grp.reset_index(drop=True)
            resident = unit_grp["Resident"].iloc[0]
            src = unit_grp["Source_File"].iloc[0]

            for fee in schedule:
                matching = unit_grp[
                    unit_grp["Category"].str.lower().apply(
                        lambda cat: any(kw in cat for kw in fee["keywords"])
                    )
                    & (unit_grp["Amount"] > 0)
                ]

                if matching.empty:
                    continue

                actual_amt = matching["Amount"].iloc[0]
                variance = abs(actual_amt - fee["amount"])

                if variance >= 1.0:
                    flags.append(
                        _make_flag(
                            prop, unit, resident,
                            "Fee Schedule Violation",
                            f"'{fee['name']}': Schedule = ${fee['amount']:.2f}/mo, "
                            f"Projection = ${actual_amt:.2f}/mo "
                            f"(variance ${variance:.2f}). Review lease addendum.",
                            variance,
                            src,
                        )
                    )

    return pd.DataFrame(flags) if flags else pd.DataFrame()


# ===========================================================================
# SECTION 6 — MANAGER OVERRIDE AUDIT
# ===========================================================================

def run_manager_override_audit(df_edits: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Uses the Edited Transactions by User report.

    Returns
    -------
    (manager_ranking DataFrame, override_log DataFrame)
    manager_ranking columns: Property, Manager_Login, Total_Events,
                              Reversals, Amount_Changes, Total_Impact
    """
    if df_edits is None or df_edits.empty:
        return pd.DataFrame(), pd.DataFrame()

    override_log = df_edits.copy()

    manager_ranking = (
        override_log.groupby(["Property", "Manager_Login"])
        .agg(
            Total_Events=("Event_Type", "count"),
            Reversals=("Event_Type", lambda x: (x == "Reversal").sum()),
            Amount_Changes=("Event_Type", lambda x: (x == "Amount Change").sum()),
            Total_Impact=("Revenue_Impact", "sum"),
        )
        .reset_index()
        .sort_values("Total_Impact", ascending=True)
    )

    return manager_ranking, override_log


# ===========================================================================
# SECTION 7 — FINANCIAL EXPOSURE AGGREGATION
# ===========================================================================

def calculate_exposure(flags_df: pd.DataFrame) -> dict:
    """Roll up exception exposure into summary DataFrames."""
    empty = pd.DataFrame()
    if flags_df is None or flags_df.empty:
        return {
            "by_property": empty,
            "by_rule": empty,
            "by_risk": empty,
            "totals": empty,
        }

    df = flags_df.copy()
    df["Amount_Impact"] = pd.to_numeric(df["Amount_Impact"], errors="coerce").fillna(0)

    by_prop = (
        df.groupby(["Property", "Risk_Level"])["Amount_Impact"]
        .agg(Exceptions="count", Total_Exposure="sum")
        .reset_index()
        .sort_values("Total_Exposure", ascending=False)
    )
    by_rule = (
        df.groupby(["Rule", "Risk_Level"])["Amount_Impact"]
        .agg(Count="count", Total_Exposure="sum")
        .reset_index()
        .sort_values("Total_Exposure", ascending=False)
    )
    by_risk = (
        df.groupby("Risk_Level")["Amount_Impact"]
        .agg(Count="count", Total_Exposure="sum")
        .reset_index()
    )
    totals = pd.DataFrame(
        [
            {
                "Total_Units_Audited": df["Unit"].nunique(),
                "Total_Exceptions": len(df),
                "Total_Exposure": round(df["Amount_Impact"].sum(), 2),
                "Critical_Flags": (df["Risk_Level"] == RISK_CRITICAL).sum(),
                "High_Flags": (df["Risk_Level"] == RISK_HIGH).sum(),
                "Medium_Flags": (df["Risk_Level"] == RISK_MEDIUM).sum(),
                "Error_Pct": round(len(df) / max(df["Unit"].nunique(), 1) * 100, 1),
            }
        ]
    )

    return {
        "by_property": by_prop,
        "by_rule": by_rule,
        "by_risk": by_risk,
        "totals": totals,
    }


# ===========================================================================
# SECTION 8 — TOP-LEVEL ORCHESTRATOR
# ===========================================================================

def run_resman_audit(data_dir: str = "data") -> dict:
    """
    Load all 6 ResMan CSV subfolders and run all audit engines.

    Parameters
    ----------
    data_dir:
        Root directory containing the 6 subfolders
        (transactions/, leases/, edits/, recurring/, rent_rolls/, activity/).

    Returns
    -------
    dict with keys:
        johns_flags     — pd.DataFrame
        daniels_flags   — pd.DataFrame
        fee_flags       — pd.DataFrame
        all_flags       — pd.DataFrame  (concatenation of the above three)
        manager_ranking — pd.DataFrame
        override_log    — pd.DataFrame
        exposure        — dict with keys: by_property, by_rule, by_risk, totals
    """
    dirs = {
        "transactions": os.path.join(data_dir, "transactions"),
        "leases": os.path.join(data_dir, "leases"),
        "edits": os.path.join(data_dir, "edits"),
        "recurring": os.path.join(data_dir, "recurring"),
        "rent_rolls": os.path.join(data_dir, "rent_rolls"),
        "activity": os.path.join(data_dir, "activity"),
    }

    df_trans = _load_transaction_list(dirs["transactions"])
    df_leases = _load_leases(dirs["leases"])
    df_edits = _load_edits(dirs["edits"])
    df_projection = _load_transaction_projection(dirs["recurring"], AUDIT_MONTH)
    df_rent_roll = _load_rent_roll(dirs["rent_rolls"])
    df_activity = _load_resident_activity(dirs["activity"])

    johns_flags = run_johns_engine(
        df_trans, df_leases,
        df_projection=df_projection,
        df_rent_roll=df_rent_roll,
    )
    daniels_flags = run_daniels_engine(
        df_projection, df_rent_roll, df_trans, df_leases, df_activity
    )
    fee_flags = run_fee_schedule_check(df_projection)
    manager_ranking, override_log = run_manager_override_audit(df_edits)

    parts = [f for f in [johns_flags, daniels_flags, fee_flags] if not f.empty]
    all_flags = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()

    exposure = calculate_exposure(all_flags)

    return {
        "johns_flags": johns_flags,
        "daniels_flags": daniels_flags,
        "fee_flags": fee_flags,
        "all_flags": all_flags,
        "manager_ranking": manager_ranking,
        "override_log": override_log,
        "exposure": exposure,
    }
