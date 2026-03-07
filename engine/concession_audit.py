"""
Concession audit engine.

Applies rule-based anomaly detection directly to a parsed ResMan
Transaction List DataFrame.  No CanonicalModel is required.
"""
from __future__ import annotations

import re
from typing import Any

import pandas as pd


# ---------------------------------------------------------------------------
# Severity → UI colour mapping
# ---------------------------------------------------------------------------

SEVERITY_COLORS: dict[str, str] = {
    "CRITICAL": "#FF4B4B",
    "HIGH": "#FF8C00",
    "MEDIUM": "#FFD700",
    "LOW": "#90EE90",
}

SEVERITY_ORDER: list[str] = ["CRITICAL", "HIGH", "MEDIUM", "LOW"]

# Rule metadata (rule_id → (label, severity))
RULE_META: dict[str, tuple[str, str]] = {
    "R1": ("Reversal Detected", "HIGH"),
    "R2": ("Move-In Special ≥ $795", "HIGH"),
    "R3": ("Excessive Concession > $1,000", "CRITICAL"),
    "R4": ("Post-Period Charge / Proration", "MEDIUM"),
    "R5": ("Duplicate Unit Entry", "MEDIUM"),
    "R6": ("Generic Description", "LOW"),
}

_MI_KEYWORDS: list[str] = ["$99", "m/i", "move in", "move-in", "special", "free"]
_MI_PATTERN = re.compile("|".join(re.escape(kw) for kw in _MI_KEYWORDS), re.IGNORECASE)


def _worst_severity(flags: list[str]) -> str | None:
    """Return the highest severity string from a list of flag IDs."""
    for sev in SEVERITY_ORDER:
        if any(f.endswith(f"_{sev}") for f in flags):
            return sev
    return None


class ConcessionAuditor:
    """
    Apply concession audit rules to a single-property transaction DataFrame.

    Parameters
    ----------
    df : pd.DataFrame
        Cleaned output from ``parse_resman_transaction_csv``.
    property_name : str
        Human-readable property name (used in reason messages).
    """

    def __init__(self, df: pd.DataFrame, property_name: str) -> None:
        self.df = df.copy()
        self.property_name = property_name

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self) -> pd.DataFrame:
        """
        Return the DataFrame with two extra columns appended:

        * ``_anomaly_flags``   – list[str] of rule IDs triggered (e.g. ``["R1_HIGH", "R3_CRITICAL"]``)
        * ``_anomaly_reasons`` – semicolon-joined human-readable reason strings
        """
        df = self.df.copy()

        # Pre-compute per-unit counts for Rule 5
        unit_counts: dict[str, int] = df["Unit"].value_counts().to_dict() if "Unit" in df.columns else {}

        all_flags: list[list[str]] = []
        all_reasons: list[str] = []

        for _, row in df.iterrows():
            flags: list[str] = []
            reasons: list[str] = []

            amount: float = float(row.get("Amount", 0) or 0)
            desc: str = str(row.get("Description", "")).strip()
            desc_lower: str = desc.lower()
            reverse_date: str = str(row.get("Reverse Date", "")).strip()
            post_charges: float = float(row.get("Post Charges", 0) or 0)
            unit: str = str(row.get("Unit", "")).strip()

            # Rule 1 — Reversal Detected (HIGH)
            if reverse_date and reverse_date not in ("nan", "0", "0.0"):
                flags.append("R1_HIGH")
                reasons.append(
                    f"Concession reversed on {reverse_date} — confirm if re-applied correctly"
                )

            # Rule 2 — Move-In Special ≥ $795 (HIGH)
            if amount >= 795 and _MI_PATTERN.search(desc_lower):
                flags.append("R2_HIGH")
                reasons.append(
                    f"Large move-in special of ${amount:,.2f} — verify lease agreement and approval"
                )

            # Rule 3 — Excessive Concession > $1,000 (CRITICAL)
            if amount > 1000:
                flags.append("R3_CRITICAL")
                reasons.append(
                    f"Concession of ${amount:,.2f} exceeds $1,000 threshold — requires COO approval"
                )

            # Rule 4 — Post Charges non-zero (MEDIUM)
            if post_charges != 0:
                flags.append("R4_MEDIUM")
                reasons.append(
                    f"Post-period charge of ${post_charges:,.2f} detected — possible proration issue"
                )

            # Rule 5 — Duplicate Unit Entry (MEDIUM)
            if unit and unit_counts.get(unit, 0) > 1:
                n = unit_counts[unit]
                flags.append("R5_MEDIUM")
                reasons.append(
                    f"Unit {unit} has {n} concession entries in the same period — possible duplicate"
                )

            # Rule 6 — Generic Description (LOW)
            if desc == "Concession - Rent":
                flags.append("R6_LOW")
                reasons.append(
                    "Generic concession description — no special or approval reference found"
                )

            all_flags.append(flags)
            all_reasons.append("; ".join(reasons))

        df["_anomaly_flags"] = all_flags
        df["_anomaly_reasons"] = all_reasons
        return df

    def summary(self) -> dict[str, Any]:
        """
        Return aggregate statistics over the audited DataFrame.

        Keys
        ----
        total_rows, flagged_rows, total_amount, amount_at_risk,
        severity_counts (dict keyed by CRITICAL / HIGH / MEDIUM / LOW)
        """
        audited = self.run()
        flagged = audited[audited["_anomaly_reasons"] != ""]

        severity_counts: dict[str, int] = {s: 0 for s in SEVERITY_ORDER}
        for flags in audited["_anomaly_flags"]:
            for flag in flags:
                sev = flag.split("_")[-1]
                if sev in severity_counts:
                    severity_counts[sev] += 1

        total_amount: float = float(audited["Amount"].sum()) if "Amount" in audited.columns else 0.0
        amount_at_risk: float = float(flagged["Amount"].sum()) if "Amount" in flagged.columns else 0.0

        return {
            "total_rows": len(audited),
            "flagged_rows": len(flagged),
            "total_amount": total_amount,
            "amount_at_risk": amount_at_risk,
            "severity_counts": severity_counts,
        }
