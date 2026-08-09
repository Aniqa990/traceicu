import duckdb

DB_PATH = "database/mimic.duckdb"

con = duckdb.connect(DB_PATH)

tables = {
    "patients": "data/mimic/hosp/patients.csv.gz",
    "admissions": "data/mimic/hosp/admissions.csv.gz",
    "transfers": "data/mimic/hosp/transfers.csv.gz",
    "labevents": "data/mimic/hosp/labevents.csv.gz",
    "d_labitems": "data/mimic/hosp/d_labitems.csv.gz",
    "emar": "data/mimic/hosp/emar.csv.gz",
    "procedures_icd": "data/mimic/hosp/procedures_icd.csv.gz",
    "d_icd_procedures": "data/mimic/hosp/d_icd_procedures.csv.gz",

    "icustays": "data/mimic/icu/icustays.csv.gz",
    "chartevents": "data/mimic/icu/chartevents.csv.gz",
    "d_items": "data/mimic/icu/d_items.csv.gz",
}

for table_name, file_path in tables.items():
    print(f"Loading {table_name}...")

    con.execute(f"""
        CREATE OR REPLACE TABLE {table_name} AS
        SELECT *
        FROM read_csv_auto('{file_path}');
    """)

    count = con.execute(
        f"SELECT COUNT(*) FROM {table_name}"
    ).fetchone()[0]

    print(f"  ✓ {count:,} rows")

con.close()

print("\nDatabase ready:", DB_PATH)