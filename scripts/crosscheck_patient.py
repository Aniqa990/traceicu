import duckdb
import pandas as pd

DB_PATH = "database/mimic.duckdb"

SUBJECT_ID = 10006053

con = duckdb.connect(DB_PATH)


def show(title, query, params=None):
    print("\n" + "=" * 80)
    print(title)
    print("=" * 80)

    df = con.execute(query, params or []).df()

    if df.empty:
        print("No rows found.")
    else:
        print(df.to_string(index=False))

    print(f"\nRows: {len(df)}")


# ---------------------------------------------------------
# 1. PATIENT
# ---------------------------------------------------------

show(
    "PATIENT",
    """
    SELECT *
    FROM patients
    WHERE subject_id = ?
    """,
    [SUBJECT_ID]
)


# ---------------------------------------------------------
# 2. ADMISSIONS
# ---------------------------------------------------------

show(
    "ADMISSIONS",
    """
    SELECT *
    FROM admissions
    WHERE subject_id = ?
    ORDER BY admittime
    """,
    [SUBJECT_ID]
)


# ---------------------------------------------------------
# 3. TRANSFERS
# ---------------------------------------------------------

show(
    "TRANSFERS",
    """
    SELECT *
    FROM transfers
    WHERE subject_id = ?
    ORDER BY intime
    """,
    [SUBJECT_ID]
)


# ---------------------------------------------------------
# 4. ICU STAYS
# ---------------------------------------------------------

show(
    "ICU STAYS",
    """
    SELECT *
    FROM icustays
    WHERE subject_id = ?
    ORDER BY intime
    """,
    [SUBJECT_ID]
)


# ---------------------------------------------------------
# 5. LAB EVENTS + DICTIONARY
# ---------------------------------------------------------

show(
    "LAB EVENTS + D_LABITEMS",
    """
    SELECT
        l.labevent_id,
        l.subject_id,
        l.hadm_id,
        l.itemid,

        d.label,
        d.fluid,
        d.category,

        l.charttime,
        l.value,
        l.valuenum,
        l.valueuom,

        l.ref_range_lower,
        l.ref_range_upper,
        l.flag

    FROM labevents l

    LEFT JOIN d_labitems d
        ON l.itemid = d.itemid

    WHERE l.subject_id = ?

    ORDER BY l.charttime
    LIMIT 100
    """,
    [SUBJECT_ID]
)


# ---------------------------------------------------------
# 6. MEDICATION EVENTS
# ---------------------------------------------------------

show(
    "MEDICATION EVENTS (EMAR)",
    """
    SELECT *
    FROM emar
    WHERE subject_id = ?
    ORDER BY charttime
    LIMIT 100
    """,
    [SUBJECT_ID]
)


# ---------------------------------------------------------
# 7. PROCEDURES + DICTIONARY
# ---------------------------------------------------------

show(
    "PROCEDURES + D_ICD_PROCEDURES",
    """
    SELECT
        p.subject_id,
        p.hadm_id,
        p.seq_num,
        p.chartdate,
        p.icd_code,
        p.icd_version,

        d.long_title

    FROM procedures_icd p

    LEFT JOIN d_icd_procedures d
        ON p.icd_code = d.icd_code
        AND p.icd_version = d.icd_version

    WHERE p.subject_id = ?

    ORDER BY p.chartdate
    """,
    [SUBJECT_ID]
)


# ---------------------------------------------------------
# 8. ICU OBSERVATIONS + D_ITEMS
# ---------------------------------------------------------

show(
    "CHARTEVENTS + D_ITEMS",
    """
    SELECT
        c.subject_id,
        c.hadm_id,
        c.stay_id,

        c.charttime,

        c.itemid,
        d.label,
        d.abbreviation,
        d.category,
        d.unitname,

        c.value,
        c.valuenum,
        c.valueuom,

        c.warning

    FROM chartevents c

    LEFT JOIN d_items d
        ON c.itemid = d.itemid

    WHERE c.subject_id = ?

    ORDER BY c.charttime

    LIMIT 100
    """,
    [SUBJECT_ID]
)


con.close()

print("\n" + "=" * 80)
print("CROSS-CHECK COMPLETE")
print("=" * 80)