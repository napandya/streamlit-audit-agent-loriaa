"""
Data normalization and summary generation for parsed documents.
"""
from typing import Optional
import pandas as pd

from ingestion.parsers import ParsedDocument


# Column alias → canonical name mappings
_COLUMN_MAP = {
    "rent": "monthly_rent",
    "monthly rent": "monthly_rent",
    "amount": "monthly_rent",
    "rent amount": "monthly_rent",
    "market rent": "market_rent",
    "unit": "unit_id",
    "unit #": "unit_id",
    "unit number": "unit_id",
    "resident": "resident_name",
    "residents": "resident_name",
    "tenant": "resident_name",
    "status": "status",
    "type": "unit_type",
    "unit type": "unit_type",
    "sq. feet": "sqft",
    "sq ft": "sqft",
    "sq feet": "sqft",
    "move in": "move_in_date",
    "move-in": "move_in_date",
    "move in date": "move_in_date",
    "lease start": "lease_start_date",
    "lease begin": "lease_start_date",
    "lease end": "lease_end_date",
    "lease expiry": "lease_end_date",
    "balance": "balance",
    "deposit": "deposit",
    "deposits": "deposit",
}


class DataProcessor:
    """
    Normalises DataFrames and produces LLM-ready summaries from ParsedDocuments.
    """

    def normalize_columns(self, df: Optional[pd.DataFrame]) -> pd.DataFrame:
        """
        Map common column aliases to standard names.

        Args:
            df: Input DataFrame. None raises ValueError.

        Returns:
            DataFrame with renamed columns.
        """
        if df is None:
            raise ValueError("normalize_columns received None — expected a DataFrame.")
        if df.empty:
            return df.copy()

        rename_map: dict[str, str] = {}
        for col in df.columns:
            lower = str(col).lower().strip()
            if lower in _COLUMN_MAP:
                canonical = _COLUMN_MAP[lower]
                # Only rename if the canonical name isn't already a column
                if canonical not in df.columns:
                    rename_map[col] = canonical
        return df.rename(columns=rename_map)

    # ------------------------------------------------------------------
    # Summary builders
    # ------------------------------------------------------------------

    def produce_summary(self, parsed_doc: Optional[ParsedDocument]) -> str:
        """
        Produce a structured text summary tailored to document type.

        Args:
            parsed_doc: A ParsedDocument (or None).

        Returns:
            A human-readable string suitable for passing to the LLM.
        """
        if parsed_doc is None:
            return "No document provided."

        doc_type = parsed_doc.document_type or "unknown"

        if doc_type == "rent_roll":
            return self._summarize_rent_roll(parsed_doc)
        if doc_type == "projection":
            return self._summarize_projection(parsed_doc)
        if doc_type == "concession":
            return self._summarize_concession(parsed_doc)

        # Generic fallback
        lines = [
            f"=== Document: {parsed_doc.file_name} (type: {doc_type}) ===",
            f"File type: {parsed_doc.file_type}",
        ]
        if parsed_doc.dataframe is not None and not parsed_doc.dataframe.empty:
            lines.append(f"Rows: {len(parsed_doc.dataframe)}")
            lines.append(f"Columns: {list(parsed_doc.dataframe.columns)}")
        if parsed_doc.raw_text:
            lines.append("\nRaw text preview (first 1000 chars):")
            lines.append(parsed_doc.raw_text[:1000])
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _summarize_rent_roll(self, doc: ParsedDocument) -> str:
        lines = [f"=== Rent Roll: {doc.file_name} ==="]

        df = doc.dataframe
        if df is None or df.empty:
            lines.append("No tabular data available.")
            lines.append(f"\nRaw text preview:\n{doc.raw_text[:1000]}")
            return "\n".join(lines)

        df = self.normalize_columns(df)
        total_rows = len(df)
        lines.append(f"Total rows: {total_rows}")

        # Deduplicate to unit level for KPI counting so that multi-charge rows
        # (e.g., Rent + Pet Fee + Concession for the same unit) don't inflate counts.
        unit_df = df
        if "unit_id" in df.columns:
            unit_df = (
                df.sort_values("unit_id")
                .drop_duplicates(subset=["unit_id"], keep="first")
            )
            total_units = len(unit_df)
            lines.append(f"Total units (unique): {total_units}")
        else:
            total_units = total_rows

        # Status counts (based on unique units, not raw rows)
        if "status" in unit_df.columns:
            status_counts = unit_df["status"].value_counts().to_dict()
            lines.append(f"Status breakdown: {status_counts}")

            status_series = unit_df["status"].astype(str).str.upper()
            vacant = int(status_series.isin(["VACANT", "V"]).sum())
            occupied = total_units - vacant
            lines.append(f"Occupied: {occupied}  |  Vacant: {vacant}")

            ue = int(status_series.isin(["UE"]).sum())
            ntv = int(status_series.isin(["NTV"]).sum())
            mtm = int(status_series.isin(["MTM"]).sum())
            lines.append(f"UE (under eviction): {ue}  |  NTV: {ntv}  |  MTM: {mtm}")

        # Balance anomalies (report per unit)
        if "balance" in unit_df.columns:
            try:
                unit_df = unit_df.copy()
                unit_df["_balance_num"] = pd.to_numeric(unit_df["balance"], errors="coerce")
                high_balance = unit_df[unit_df["_balance_num"] > 1000]
                if not high_balance.empty:
                    lines.append(f"\nUnits with balance > $1,000: {len(high_balance)}")
                    for _, row in high_balance.head(10).iterrows():
                        unit = row.get("unit_id", "?")
                        bal = row["_balance_num"]
                        status = row.get("status", "?")
                        lines.append(f"  Unit {unit} | Status: {status} | Balance: ${bal:,.2f}")
            except Exception:
                pass

        # Zero charged rent (use monthly_rent if available, else skip)
        if "monthly_rent" in unit_df.columns:
            try:
                unit_df = unit_df.copy()
                unit_df["_rent_num"] = pd.to_numeric(unit_df["monthly_rent"], errors="coerce")
                zero_rent = unit_df[(unit_df["_rent_num"] == 0) | unit_df["_rent_num"].isna()]
                if not zero_rent.empty:
                    lines.append(f"\nUnits with zero/missing charged rent: {len(zero_rent)}")
            except Exception:
                pass

        return "\n".join(lines)

    def _summarize_projection(self, doc: ParsedDocument) -> str:
        lines = [f"=== Projection: {doc.file_name} ==="]

        df = doc.dataframe
        if df is None or df.empty:
            lines.append("No tabular data available.")
            lines.append(f"\nRaw text preview:\n{doc.raw_text[:1000]}")
            return "\n".join(lines)

        lines.append(f"Rows: {len(df)}  |  Columns: {len(df.columns)}")
        lines.append(f"Column names: {list(df.columns)}")

        # Identify month-like columns
        from utils.helpers import parse_month
        month_cols = [c for c in df.columns if parse_month(str(c)) is not None]
        if month_cols:
            lines.append(f"\nProjection months detected: {month_cols}")

            # Prefer the "Property Total" row for per-month values
            from utils.helpers import find_property_total_row
            total_row = find_property_total_row(df)

            source = total_row if (total_row is not None and not total_row.empty) else df
            for col in month_cols:
                try:
                    total = pd.to_numeric(source[col], errors="coerce").sum()
                    lines.append(f"  {col}: ${total:,.2f}")
                except Exception:
                    pass
        else:
            lines.append("\nNo month columns detected — raw preview:")
            lines.append(doc.raw_text[:800])

        return "\n".join(lines)

    def _summarize_concession(self, doc: ParsedDocument) -> str:
        lines = [f"=== Concession Document: {doc.file_name} ==="]

        df = doc.dataframe
        if df is None or df.empty:
            lines.append("No tabular data available.")
            lines.append(f"\nRaw text preview:\n{doc.raw_text[:1000]}")
            return "\n".join(lines)

        lines.append(f"Source file: {doc.file_name}")
        lines.append(f"Total concession line items: {len(df)}")
        lines.append(f"Columns: {list(df.columns)}")

        # --- Pre-computed statistics the LLM should use ---
        if "Amount" in df.columns:
            amounts = pd.to_numeric(
                df["Amount"].astype(str).str.replace(",", "").str.replace("$", ""),
                errors="coerce",
            ).fillna(0)
            lines.append(f"\nTotal concession amount: ${amounts.sum():,.2f}")
            lines.append(f"Average concession: ${amounts.mean():,.2f}")
            lines.append(f"Max single concession: ${amounts.max():,.2f}")
            lines.append(f"Min single concession: ${amounts.min():,.2f}")
            large = (amounts > 1000).sum()
            if large:
                lines.append(f"⚠ Concessions > $1,000: {large}")

        if "Unit" in df.columns:
            unique_units = df["Unit"].nunique()
            dup_units = df["Unit"].value_counts()
            dup_units = dup_units[dup_units > 1]
            lines.append(f"\nUnique units with concessions: {unique_units}")
            if not dup_units.empty:
                lines.append(f"⚠ Units with MULTIPLE concessions: {len(dup_units)}")
                for unit, count in dup_units.head(10).items():
                    lines.append(f"  Unit {unit}: {count} entries")

        if "Description" in df.columns:
            desc_lower = df["Description"].astype(str).str.lower()
            n999 = desc_lower.str.contains("999|\\$999", na=False, regex=True).sum()
            n_movein = desc_lower.str.contains("move.?in|m/i|\\$99 total", na=False, regex=True).sum()
            n_generic = (df["Description"].astype(str).str.strip() == "Concession - Rent").sum()
            if n999:
                lines.append(f"⚠ $999 specials detected: {n999}")
            if n_movein:
                lines.append(f"⚠ Move-in specials detected: {n_movein}")
            if n_generic:
                lines.append(f"⚠ Generic 'Concession - Rent' (no detail): {n_generic}")

        if "Reverse Date" in df.columns:
            rev_col = df["Reverse Date"].astype(str).str.strip()
            reversed_count = ((rev_col != "") & (rev_col != "nan") & (rev_col != "0")).sum()
            not_reversed = len(df) - reversed_count
            lines.append(f"\nReversed concessions: {reversed_count}")
            lines.append(f"Active (not reversed) concessions: {not_reversed}")

        # Provide row-numbered concession data so the LLM can cite specific rows
        lines.append(f"\nDetailed concession rows (with CSV row numbers from {doc.file_name}):")
        for i, (_idx, row) in enumerate(df.iterrows()):
            row_num = i + 2  # +2 for 1-indexed header row in CSV
            row_vals = " | ".join(str(v) for v in row.values if str(v) != "nan")
            lines.append(f"  [Row {row_num}] {row_vals}")
            if i >= 150:
                lines.append(f"  ... ({len(df) - 150} more rows omitted)")
                break

        return "\n".join(lines)
