"""
DuckDB connection management.

Every MIMIC-IV table is registered as a DuckDB VIEW directly over the
source CSV (or CSV.GZ) file. Nothing is copied or transformed on load --
that keeps the source data immutable and makes every downstream query
traceable back to a specific file.
"""

from __future__ import annotations

from pathlib import Path

import duckdb

from config import HOSP_DIR, ICU_DIR

HOSP_TABLES = [
    "patients",
    "admissions",
    "transfers",
    "labevents",
    "d_labitems",
    "prescriptions",
    "emar",
    "diagnoses_icd",
    "d_icd_diagnoses",
    "procedures_icd",
    "d_icd_procedures",
]

ICU_TABLES = [
    "icustays",
    "chartevents",
    "d_items",
    "inputevents",
    "outputevents",
    "procedureevents",
]


def get_connection(read_only_data: bool = True) -> duckdb.DuckDBPyConnection:
    """Open an in-memory DuckDB connection with every available MIMIC
    table registered as a view. Missing tables are skipped with a
    warning rather than raising, so the backend degrades gracefully if
    you only copied a subset of the demo (e.g. no ICU module)."""
    con = duckdb.connect(database=":memory:")
    _register_dir(con, HOSP_DIR, HOSP_TABLES)
    _register_dir(con, ICU_DIR, ICU_TABLES)
    return con


def _register_dir(con: duckdb.DuckDBPyConnection, directory: Path, tables: list[str]) -> list[str]:
    loaded = []
    for name in tables:
        path = _find_file(directory, name)
        if path is None:
            print(f"[traceicu] warning: table '{name}' not found under {directory}, skipping")
            continue
        escaped_path = str(path).replace("'", "''")
        con.execute(
            f"CREATE OR REPLACE VIEW {name} AS "
            f"SELECT * FROM read_csv_auto('{escaped_path}', ignore_errors=true, sample_size=-1)"
        )
        loaded.append(name)
    return loaded


def _find_file(directory: Path, table_name: str) -> Path | None:
    for ext in (".csv.gz", ".csv"):
        candidate = directory / f"{table_name}{ext}"
        if candidate.exists():
            return candidate
    return None


def loaded_tables(con: duckdb.DuckDBPyConnection) -> list[str]:
    """Views actually registered in this connection (from the DuckDB catalog,
    not a Python attribute -- DuckDB connection objects don't support those)."""
    rows = con.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_type = 'VIEW'"
    ).fetchall()
    return sorted(r[0] for r in rows)


def query(con: duckdb.DuckDBPyConnection, sql: str, params: list | None = None) -> list[dict]:
    """Run a query and return rows as a list of plain dicts (column name -> value)."""
    cur = con.execute(sql, params or [])
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]