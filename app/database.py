from pathlib import Path
import duckdb

DB_PATH = Path(__file__).resolve().parent.parent / "database" / "mimic.duckdb"


def get_connection():
    return duckdb.connect(str(DB_PATH), read_only=True)