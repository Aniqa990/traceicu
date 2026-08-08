import duckdb

con = duckdb.connect("database/mimic.duckdb")

tables = [
    "patients",
    "admissions",
    "transfers",
    "icustays",
    "labevents",
    "d_labitems",
    "emar",
    "procedures_icd",
    "d_icd_procedures",
    "chartevents",
    "d_items",
]

for table in tables:
    print("\n" + "=" * 60)
    print(table)
    print("=" * 60)

    columns = con.execute(
        f"DESCRIBE {table}"
    ).fetchall()

    for column in columns:
        print(f"{column[0]:25} {column[1]}")

con.close()