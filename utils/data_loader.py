"""
Data-loading helpers for the audit application.
"""
from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)


def load_resman_csvs_from_data_dir(
    data_dir: str = "data",
) -> list[tuple[str, pd.DataFrame]]:
    """
    Scan *data_dir* for ResMan Transaction List CSV files and parse them.

    Parameters
    ----------
    data_dir:
        Directory to scan (default: ``"data"``).

    Returns
    -------
    List of ``(property_name, dataframe)`` tuples, one per matched file.
    Returns an empty list if the directory does not exist or contains no
    matching files.
    """
    from ingestion.resman_transaction_parser import parse_resman_transaction_csv

    data_path = Path(data_dir)
    if not data_path.exists():
        logger.warning("data_loader: directory '%s' does not exist.", data_dir)
        return []

    csv_files = sorted(data_path.glob("*Transaction List (Credits)*.csv"))
    if not csv_files:
        logger.info("data_loader: no matching CSVs found in '%s'.", data_dir)
        return []

    results: list[tuple[str, pd.DataFrame]] = []
    for csv_file in csv_files:
        try:
            property_name, df = parse_resman_transaction_csv(str(csv_file))
            results.append((property_name, df))
            logger.info("data_loader: loaded '%s' → %s (%d rows)", csv_file.name, property_name, len(df))
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "data_loader: failed to parse '%s' (full path: '%s'): %s",
                csv_file.name,
                csv_file,
                exc,
                exc_info=True,
            )

    return results
