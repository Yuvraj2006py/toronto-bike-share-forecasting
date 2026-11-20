"""DuckDB connection helpers.

Why a small helper file: every notebook/script should open the same database
path so Phase 1–6 share one source of truth under data/processed/.
"""

from __future__ import annotations

from pathlib import Path

import duckdb

# Project root = parent of src/
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_RAW = PROJECT_ROOT / "data" / "raw"
DATA_PROCESSED = PROJECT_ROOT / "data" / "processed"
DB_PATH = DATA_PROCESSED / "bikeshare.duckdb"


def get_connection(read_only: bool = False) -> duckdb.DuckDBPyConnection:
    """Open (or create) the project DuckDB file."""
    DATA_PROCESSED.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(DB_PATH), read_only=read_only)
