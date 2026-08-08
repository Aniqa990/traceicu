from pathlib import Path

import duckdb

from app.config import settings


def csv_path(directory: Path, filename: str) -> str:
    path = directory / filename

    if not path.exists():
        raise FileNotFoundError(f"Missing MIMIC file: {path}")

    # DuckDB SQL string literal escaping
    return str(path.resolve()).replace("'", "''")


def main():
    settings.hosp_path.mkdir(parents=True, exist_ok=True)
    settings.icu_path.mkdir(parents=True, exist_ok=True)

    Path(settings.duckdb_path).parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    db = duckdb.connect(settings.duckdb_path)

    hosp = settings.hosp_path
    icu = settings.icu_path

    views = {
        "patients": (
            f"'{csv_path(hosp, 'patients.csv.gz')}'"
        ),
        "admissions": (
            f"'{csv_path(hosp, 'admissions.csv.gz')}'"
        ),
        "transfers": (
            f"'{csv_path(hosp, 'transfers.csv.gz')}'"
        ),
        "labevents": (
            f"'{csv_path(hosp, 'labevents.csv.gz')}'"
        ),
        "d_labitems": (
            f"'{csv_path(hosp, 'd_labitems.csv.gz')}'"
        ),
        "emar": (
            f"'{csv_path(hosp, 'emar.csv.gz')}'"
        ),
        "prescriptions": (
            f"'{csv_path(hosp, 'prescriptions.csv.gz')}'"
        ),
        "diagnoses_icd": (
            f"'{csv_path(hosp, 'diagnoses_icd.csv.gz')}'"
        ),
        "procedures_icd": (
            f"'{csv_path(hosp, 'procedures_icd.csv.gz')}'"
        ),
        "d_icd_diagnoses": (
            f"'{csv_path(hosp, 'd_icd_diagnoses.csv.gz')}'"
        ),
        "d_icd_procedures": (
            f"'{csv_path(hosp, 'd_icd_procedures.csv.gz')}'"
        ),
        "icustays": (
            f"'{csv_path(icu, 'icustays.csv.gz')}'"
        ),
        "chartevents": (
            f"'{csv_path(icu, 'chartevents.csv.gz')}'"
        ),
        "d_items": (
            f"'{csv_path(icu, 'd_items.csv.gz')}'"
        ),
        "procedureevents": (
            f"'{csv_path(icu, 'procedureevents.csv.gz')}'"
        ),
    }

    for table_name, path in views.items():
        print(f"Creating view: {table_name}")

        db.execute(
            f"""
            CREATE OR REPLACE VIEW {table_name} AS
            SELECT *
            FROM read_csv_auto(
                {path},
                header = true,
                ignore_errors = false
            );
            """
        )

    db.execute(
        """
        CREATE TABLE IF NOT EXISTS app_metadata (
            key VARCHAR PRIMARY KEY,
            value VARCHAR
        );
        """
    )

    db.execute(
        """
        INSERT OR REPLACE INTO app_metadata
        VALUES
            ('dataset', 'MIMIC-IV Clinical Database Demo'),
            ('version', '2.2'),
            ('timeline_backend', 'DuckDB'),
            ('source_policy', 'Original source tables preserved');
        """
    )

    db.close()

    print()
    print("DuckDB initialized successfully.")
    print(f"Database: {settings.duckdb_path}")


if __name__ == "__main__":
    main()