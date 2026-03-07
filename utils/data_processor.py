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
    # ResMan-specific aliases
    "sq. feet": "sqft",
    "sq ft": "sqft",
    "sq.ft": "sqft",
    "sqft": "sqft",
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

            # Use "Property Total" row if present to avoid double-counting individual
            # unit rows alongside aggregate totals.
            first_col = df.columns[0]
            total_mask = df[first_col].astype(str).str.lower().str.contains(
                "property total", na=False
            )
            property_total_row = df[total_mask].iloc[0] if total_mask.any() else None

            for col in month_cols:
                try:
                    if property_total_row is not None:
                        val = pd.to_numeric(property_total_row[col], errors="coerce")
                    else:
                        val = pd.to_numeric(df[col], errors="coerce").sum()
                    if pd.notna(val):
                        lines.append(f"  {col}: ${val:,.2f}")
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

        lines.append(f"Total concession line items: {len(df)}")
        lines.append(f"Columns: {list(df.columns)}")
        lines.append("\nAll concession rows:")
        lines.append(df.to_string(index=False, max_rows=50))

        return "\n".join(lines)
