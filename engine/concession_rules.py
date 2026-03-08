"""
Deterministic concession-audit rules for ResMan Transaction List (Credits) CSVs.

Each rule scans a single property's DataFrame and returns structured findings
with row-level evidence.  The engine is designed to run **before** the LLM so
that the AI receives only pre-computed stats and flagged rows instead of the
full CSV.

Rules implemented
-----------------
CONC-001  Excessive single concession (> threshold, default $1 000)
CONC-002  $999 special-rate concessions
CONC-003  Move-in specials ($99 / $0 total move-in)
CONC-004  Reversed concessions (Reverse Date populated)
CONC-005  Duplicate unit concessions (same unit, multiple rows in period)
CONC-006  Generic / vague descriptions ("Concession - Rent" with no detail)
CONC-007  High property-level concession total (> 2× median across properties)
CONC-008  Negative amounts (possible data-entry or reversal error)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

import pandas as pd


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ConcessionFinding:
    """One deterministic finding for a single property's concession data."""

    rule_id: str
    rule_name: str
    severity: str          # critical | high | medium | low
    description: str       # human-readable summary
    property_name: str
    source_file: str
    units: List[str] = field(default_factory=list)
    rows: List[int] = field(default_factory=list)
    evidence: List[dict] = field(default_factory=list)
    # Pre-formatted detail the AI can cite directly
    detail: str = ""


@dataclass
class PropertyStats:
    """Pre-computed statistics for one property's concession CSV."""

    property_name: str
    source_file: str
    total_rows: int = 0
    total_amount: float = 0.0
    avg_amount: float = 0.0
    max_amount: float = 0.0
    min_amount: float = 0.0
    reversed_count: int = 0
    active_count: int = 0
    unique_units: int = 0
    multi_concession_units: int = 0
    specials_999_count: int = 0
    move_in_count: int = 0
    generic_desc_count: int = 0
    large_concession_count: int = 0
    negative_amount_count: int = 0


# ---------------------------------------------------------------------------
# Thresholds (can be overridden by caller)
# ---------------------------------------------------------------------------

DEFAULT_EXCESSIVE_THRESHOLD = 1000.0   # dollars
DEFAULT_HIGH_PROPERTY_MULTIPLIER = 2.0  # flag property if total > 2× median


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class ConcessionRulesEngine:
    """
    Run deterministic concession rules against one *or many* property
    DataFrames.  Call ``run_all()`` to get ``(findings, stats_per_property)``.
    """

    def __init__(
        self,
        *,
        excessive_threshold: float = DEFAULT_EXCESSIVE_THRESHOLD,
        high_property_multiplier: float = DEFAULT_HIGH_PROPERTY_MULTIPLIER,
    ):
        self.excessive_threshold = excessive_threshold
        self.high_property_multiplier = high_property_multiplier

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run_all(
        self,
        property_dfs: List[tuple[str, str, pd.DataFrame]],
    ) -> tuple[List[ConcessionFinding], List[PropertyStats]]:
        """
        Run every rule across all properties.

        Parameters
        ----------
        property_dfs:
            List of ``(property_name, source_file, dataframe)`` tuples.

        Returns
        -------
        (findings, stats)  where *findings* is the flat list of flagged items
        and *stats* is one ``PropertyStats`` per property.
        """
        all_findings: List[ConcessionFinding] = []
        all_stats: List[PropertyStats] = []

        for prop_name, src_file, df in property_dfs:
            if df is None or df.empty:
                continue
            stats = self._compute_stats(prop_name, src_file, df)
            all_stats.append(stats)
            all_findings.extend(self._run_property_rules(prop_name, src_file, df, stats))

        # Cross-property rule (CONC-007) needs the full stats list
        all_findings.extend(self._check_high_property_total(all_stats))

        return all_findings, all_stats

    # ------------------------------------------------------------------
    # Per-property rules
    # ------------------------------------------------------------------

    def _run_property_rules(
        self,
        prop: str,
        src: str,
        df: pd.DataFrame,
        stats: PropertyStats,
    ) -> List[ConcessionFinding]:
        findings: List[ConcessionFinding] = []
        amounts = self._amounts(df)
        desc_lower = self._desc_lower(df)

        findings.extend(self._conc001_excessive(prop, src, df, amounts))
        findings.extend(self._conc002_999_specials(prop, src, df, desc_lower))
        findings.extend(self._conc003_move_in(prop, src, df, desc_lower))
        findings.extend(self._conc004_reversed(prop, src, df))
        findings.extend(self._conc005_duplicate_units(prop, src, df))
        findings.extend(self._conc006_generic_desc(prop, src, df, desc_lower))
        findings.extend(self._conc008_negative_amounts(prop, src, df, amounts))

        return findings

    # -- CONC-001: Excessive single concession --------------------------

    def _conc001_excessive(
        self, prop: str, src: str, df: pd.DataFrame, amounts: pd.Series,
    ) -> List[ConcessionFinding]:
        mask = amounts > self.excessive_threshold
        if not mask.any():
            return []
        rows_idx = df.index[mask]
        evidence = []
        for idx in rows_idx:
            evidence.append(self._row_evidence(df, idx))
        units = sorted({str(df.at[idx, "Unit"]) for idx in rows_idx} if "Unit" in df.columns else [])
        rows = [int(idx) + 2 for idx in rows_idx]
        return [ConcessionFinding(
            rule_id="CONC-001",
            rule_name="Excessive Concession",
            severity="high",
            description=(
                f"{len(rows_idx)} concession(s) exceed ${self.excessive_threshold:,.0f} "
                f"across {len(units)} unit(s)"
            ),
            property_name=prop,
            source_file=src,
            units=units,
            rows=rows,
            evidence=evidence,
        )]

    # -- CONC-002: $999 specials ----------------------------------------

    def _conc002_999_specials(
        self, prop: str, src: str, df: pd.DataFrame, desc_lower: pd.Series,
    ) -> List[ConcessionFinding]:
        mask = desc_lower.str.contains(r"999|\$999", na=False, regex=True)
        if not mask.any():
            return []
        rows_idx = df.index[mask]
        evidence = [self._row_evidence(df, idx) for idx in rows_idx]
        units = self._units_for(df, rows_idx)
        return [ConcessionFinding(
            rule_id="CONC-002",
            rule_name="$999 Special-Rate Concession",
            severity="high",
            description=f"{len(rows_idx)} $999 special-rate concession(s) on {len(units)} unit(s)",
            property_name=prop,
            source_file=src,
            units=units,
            rows=[int(i) + 2 for i in rows_idx],
            evidence=evidence,
        )]

    # -- CONC-003: Move-in specials -------------------------------------

    def _conc003_move_in(
        self, prop: str, src: str, df: pd.DataFrame, desc_lower: pd.Series,
    ) -> List[ConcessionFinding]:
        mask = desc_lower.str.contains(r"move.?in|m/i|\$99 total|\$0 total", na=False, regex=True)
        if not mask.any():
            return []
        rows_idx = df.index[mask]
        evidence = [self._row_evidence(df, idx) for idx in rows_idx]
        units = self._units_for(df, rows_idx)
        return [ConcessionFinding(
            rule_id="CONC-003",
            rule_name="Move-In Special",
            severity="medium",
            description=f"{len(rows_idx)} move-in special(s) on {len(units)} unit(s)",
            property_name=prop,
            source_file=src,
            units=units,
            rows=[int(i) + 2 for i in rows_idx],
            evidence=evidence,
        )]

    # -- CONC-004: Reversed concessions ---------------------------------

    def _conc004_reversed(
        self, prop: str, src: str, df: pd.DataFrame,
    ) -> List[ConcessionFinding]:
        if "Reverse Date" not in df.columns:
            return []
        rev = df["Reverse Date"].astype(str).str.strip()
        mask = (rev != "") & (rev != "nan") & (rev != "0") & (rev != "0.0")
        if not mask.any():
            return []
        rows_idx = df.index[mask]
        evidence = [self._row_evidence(df, idx) for idx in rows_idx]
        units = self._units_for(df, rows_idx)
        total_rows = len(df)
        rev_count = int(mask.sum())
        pct = rev_count / total_rows * 100 if total_rows else 0
        sev = "high" if pct > 50 else "medium"
        return [ConcessionFinding(
            rule_id="CONC-004",
            rule_name="Reversed Concession",
            severity=sev,
            description=(
                f"{rev_count} of {total_rows} concessions reversed ({pct:.0f}%) "
                f"across {len(units)} unit(s)"
            ),
            property_name=prop,
            source_file=src,
            units=units,
            rows=[int(i) + 2 for i in rows_idx],
            evidence=evidence,
        )]

    # -- CONC-005: Duplicate unit concessions ---------------------------

    def _conc005_duplicate_units(
        self, prop: str, src: str, df: pd.DataFrame,
    ) -> List[ConcessionFinding]:
        if "Unit" not in df.columns:
            return []
        counts = df["Unit"].value_counts()
        dups = counts[counts > 1]
        if dups.empty:
            return []
        dup_units = sorted(str(u) for u in dups.index)
        # Collect evidence rows for duplicate units
        dup_mask = df["Unit"].isin(dups.index)
        rows_idx = df.index[dup_mask]
        evidence = [self._row_evidence(df, idx) for idx in rows_idx]
        detail_parts = [f"Unit {u}: {c} entries" for u, c in dups.head(15).items()]
        return [ConcessionFinding(
            rule_id="CONC-005",
            rule_name="Duplicate Unit Concessions",
            severity="medium",
            description=(
                f"{len(dup_units)} unit(s) with multiple concessions in period"
            ),
            property_name=prop,
            source_file=src,
            units=dup_units,
            rows=[int(i) + 2 for i in rows_idx],
            evidence=evidence,
            detail="; ".join(detail_parts),
        )]

    # -- CONC-006: Generic descriptions ---------------------------------

    def _conc006_generic_desc(
        self, prop: str, src: str, df: pd.DataFrame, desc_lower: pd.Series,
    ) -> List[ConcessionFinding]:
        if "Description" not in df.columns:
            return []
        raw_desc = df["Description"].astype(str).str.strip()
        mask = raw_desc.str.lower().isin(["concession - rent", ""])
        if not mask.any():
            return []
        rows_idx = df.index[mask]
        evidence = [self._row_evidence(df, idx) for idx in rows_idx]
        units = self._units_for(df, rows_idx)
        return [ConcessionFinding(
            rule_id="CONC-006",
            rule_name="Generic / Vague Description",
            severity="low",
            description=(
                f"{len(rows_idx)} concession(s) with generic 'Concession - Rent' "
                f"description (no business justification)"
            ),
            property_name=prop,
            source_file=src,
            units=units,
            rows=[int(i) + 2 for i in rows_idx],
            evidence=evidence,
        )]

    # -- CONC-008: Negative amounts -------------------------------------

    def _conc008_negative_amounts(
        self, prop: str, src: str, df: pd.DataFrame, amounts: pd.Series,
    ) -> List[ConcessionFinding]:
        mask = amounts < 0
        if not mask.any():
            return []
        rows_idx = df.index[mask]
        evidence = [self._row_evidence(df, idx) for idx in rows_idx]
        units = self._units_for(df, rows_idx)
        return [ConcessionFinding(
            rule_id="CONC-008",
            rule_name="Negative Concession Amount",
            severity="medium",
            description=(
                f"{len(rows_idx)} concession(s) with negative amounts "
                f"(possible reversal entry or data error)"
            ),
            property_name=prop,
            source_file=src,
            units=units,
            rows=[int(i) + 2 for i in rows_idx],
            evidence=evidence,
        )]

    # -- CONC-007: High property total (cross-property) -----------------

    def _check_high_property_total(
        self, all_stats: List[PropertyStats],
    ) -> List[ConcessionFinding]:
        if len(all_stats) < 2:
            return []
        totals = [s.total_amount for s in all_stats]
        median_total = sorted(totals)[len(totals) // 2]
        if median_total <= 0:
            return []
        threshold = median_total * self.high_property_multiplier

        findings: List[ConcessionFinding] = []
        for s in all_stats:
            if s.total_amount > threshold:
                findings.append(ConcessionFinding(
                    rule_id="CONC-007",
                    rule_name="High Property Concession Total",
                    severity="high",
                    description=(
                        f"{s.property_name}: total concessions ${s.total_amount:,.0f} "
                        f"exceed {self.high_property_multiplier:.0f}× the portfolio median "
                        f"(${median_total:,.0f})"
                    ),
                    property_name=s.property_name,
                    source_file=s.source_file,
                ))
        return findings

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _amounts(df: pd.DataFrame) -> pd.Series:
        if "Amount" not in df.columns:
            return pd.Series(dtype=float)
        return pd.to_numeric(
            df["Amount"].astype(str).str.replace(",", "").str.replace("$", ""),
            errors="coerce",
        ).fillna(0.0)

    @staticmethod
    def _desc_lower(df: pd.DataFrame) -> pd.Series:
        if "Description" not in df.columns:
            return pd.Series(dtype=str)
        return df["Description"].astype(str).str.lower()

    @staticmethod
    def _units_for(df: pd.DataFrame, rows_idx) -> List[str]:
        if "Unit" not in df.columns:
            return []
        return sorted({str(df.at[idx, "Unit"]) for idx in rows_idx})

    @staticmethod
    def _row_evidence(df: pd.DataFrame, idx) -> dict:
        """Build a compact evidence dict for a single row."""
        ev: dict = {"row": int(idx) + 2}
        for col in ("Unit", "Name", "Description", "Amount", "Reverse Date", "Category"):
            if col in df.columns:
                val = df.at[idx, col]
                ev[col.lower().replace(" ", "_")] = str(val) if pd.notna(val) else ""
        return ev

    def _compute_stats(
        self, prop: str, src: str, df: pd.DataFrame,
    ) -> PropertyStats:
        amounts = self._amounts(df)
        desc_lower = self._desc_lower(df)

        reversed_count = 0
        if "Reverse Date" in df.columns:
            rev = df["Reverse Date"].astype(str).str.strip()
            reversed_count = int(((rev != "") & (rev != "nan") & (rev != "0") & (rev != "0.0")).sum())

        multi_units = 0
        unique_units = 0
        if "Unit" in df.columns:
            vc = df["Unit"].value_counts()
            unique_units = len(vc)
            multi_units = int((vc > 1).sum())

        return PropertyStats(
            property_name=prop,
            source_file=src,
            total_rows=len(df),
            total_amount=float(amounts.sum()),
            avg_amount=float(amounts.mean()) if len(amounts) else 0.0,
            max_amount=float(amounts.max()) if len(amounts) else 0.0,
            min_amount=float(amounts.min()) if len(amounts) else 0.0,
            reversed_count=reversed_count,
            active_count=len(df) - reversed_count,
            unique_units=unique_units,
            multi_concession_units=multi_units,
            specials_999_count=int(desc_lower.str.contains(r"999|\$999", na=False, regex=True).sum()),
            move_in_count=int(desc_lower.str.contains(r"move.?in|m/i|\$99 total", na=False, regex=True).sum()),
            generic_desc_count=int(
                (df["Description"].astype(str).str.strip().str.lower().isin(["concession - rent", ""])).sum()
            ) if "Description" in df.columns else 0,
            large_concession_count=int((amounts > self.excessive_threshold).sum()),
            negative_amount_count=int((amounts < 0).sum()),
        )


# ---------------------------------------------------------------------------
# Convenience: format findings + stats into a compact AI-ready summary
# ---------------------------------------------------------------------------

def format_for_llm(
    findings: List[ConcessionFinding],
    stats: List[PropertyStats],
) -> str:
    """
    Produce a structured text block that gives the LLM:
    1. Per-property stats (so it knows the full picture)
    2. Only the flagged rows (so it doesn't have to scan raw data)

    This replaces sending the entire CSV contents to the LLM.
    """
    lines: list[str] = []

    # --- Portfolio overview ---
    lines.append("=== CONCESSION AUDIT — DETERMINISTIC PRE-SCAN RESULTS ===")
    lines.append(f"Properties analysed: {len(stats)}")
    total_rows = sum(s.total_rows for s in stats)
    total_amount = sum(s.total_amount for s in stats)
    total_findings = len(findings)
    lines.append(f"Total concession rows: {total_rows}")
    lines.append(f"Total concession amount: ${total_amount:,.2f}")
    lines.append(f"Deterministic findings: {total_findings}")
    lines.append("")

    # --- Per-property stats ---
    for s in stats:
        lines.append(f"--- {s.property_name} ({s.source_file}) ---")
        lines.append(f"  Rows: {s.total_rows} | Amount: ${s.total_amount:,.2f} (avg ${s.avg_amount:,.2f})")
        lines.append(f"  Max: ${s.max_amount:,.2f} | Min: ${s.min_amount:,.2f}")
        lines.append(f"  Unique units: {s.unique_units} | Multi-concession units: {s.multi_concession_units}")
        lines.append(f"  Reversed: {s.reversed_count} | Active: {s.active_count}")
        lines.append(f"  $999 specials: {s.specials_999_count} | Move-in specials: {s.move_in_count}")
        lines.append(f"  Generic descriptions: {s.generic_desc_count} | Large (>${DEFAULT_EXCESSIVE_THRESHOLD:,.0f}): {s.large_concession_count}")
        lines.append(f"  Negative amounts: {s.negative_amount_count}")
        lines.append("")

    # --- Flagged findings with evidence rows ---
    if findings:
        lines.append("=== FLAGGED FINDINGS (review and enrich with narrative) ===")
        lines.append("")
        for f in findings:
            lines.append(f"[{f.rule_id}] {f.rule_name} — {f.severity.upper()}")
            lines.append(f"  Property: {f.property_name}")
            lines.append(f"  Source: {f.source_file}")
            lines.append(f"  {f.description}")
            if f.units:
                lines.append(f"  Affected units: {', '.join(f.units[:20])}")
            if f.rows:
                rows_str = ", ".join(str(r) for r in f.rows[:20])
                if len(f.rows) > 20:
                    rows_str += f" … +{len(f.rows) - 20} more"
                lines.append(f"  Rows: {rows_str}")
            if f.detail:
                lines.append(f"  Detail: {f.detail}")
            # Include up to 5 evidence rows so AI can cite specifics
            for ev in f.evidence[:5]:
                ev_parts = []
                for k, v in ev.items():
                    if v and str(v).strip() and k != "row":
                        ev_parts.append(f"{k}={v}")
                lines.append(f"    Row {ev.get('row', '?')}: {' | '.join(ev_parts)}")
            if len(f.evidence) > 5:
                lines.append(f"    … +{len(f.evidence) - 5} more rows")
            lines.append("")

    else:
        lines.append("No deterministic findings flagged.")

    return "\n".join(lines)
