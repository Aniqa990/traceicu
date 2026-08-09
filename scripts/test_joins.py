import duckdb

con = duckdb.connect("database/mimic.duckdb")


# ---------------------------------------------------------
# 1. LABEVENTS → D_LABITEMS
# ---------------------------------------------------------

print("\n" + "=" * 60)
print("1. LABEVENTS → D_LABITEMS")
print("=" * 60)

result = con.execute("""
    SELECT
        COUNT(*) AS total_labevents,
        COUNT(d.itemid) AS matched_dictionary_rows,
        COUNT(*) - COUNT(d.itemid) AS unmatched_rows
    FROM labevents l
    LEFT JOIN d_labitems d
        ON l.itemid = d.itemid
""").fetchone()

print(f"Total labevents:       {result[0]:,}")
print(f"Matched dictionary:    {result[1]:,}")
print(f"Unmatched:              {result[2]:,}")


# Show examples
print("\nExample lab rows:")

rows = con.execute("""
    SELECT
        l.labevent_id,
        l.subject_id,
        l.hadm_id,
        l.itemid,
        d.label,
        l.charttime,
        l.value,
        l.valuenum,
        l.valueuom
    FROM labevents l
    LEFT JOIN d_labitems d
        ON l.itemid = d.itemid
    LIMIT 5
""").fetchall()

for row in rows:
    print(row)


# ---------------------------------------------------------
# 2. CHARTEVENTS → D_ITEMS
# ---------------------------------------------------------

print("\n" + "=" * 60)
print("2. CHARTEVENTS → D_ITEMS")
print("=" * 60)

result = con.execute("""
    SELECT
        COUNT(*) AS total_chartevents,
        COUNT(d.itemid) AS matched_dictionary_rows,
        COUNT(*) - COUNT(d.itemid) AS unmatched_rows
    FROM chartevents c
    LEFT JOIN d_items d
        ON c.itemid = d.itemid
""").fetchone()

print(f"Total chartevents:     {result[0]:,}")
print(f"Matched dictionary:    {result[1]:,}")
print(f"Unmatched:              {result[2]:,}")


print("\nExample chartevent rows:")

rows = con.execute("""
    SELECT
        c.subject_id,
        c.hadm_id,
        c.stay_id,
        c.itemid,
        d.label,
        c.charttime,
        c.value,
        c.valuenum,
        c.valueuom
    FROM chartevents c
    LEFT JOIN d_items d
        ON c.itemid = d.itemid
    LIMIT 5
""").fetchall()

for row in rows:
    print(row)


# ---------------------------------------------------------
# 3. PROCEDURES_ICD → D_ICD_PROCEDURES
# ---------------------------------------------------------

print("\n" + "=" * 60)
print("3. PROCEDURES_ICD → D_ICD_PROCEDURES")
print("=" * 60)

result = con.execute("""
    SELECT
        COUNT(*) AS total_procedures,
        COUNT(d.icd_code) AS matched_dictionary_rows,
        COUNT(*) - COUNT(d.icd_code) AS unmatched_rows
    FROM procedures_icd p
    LEFT JOIN d_icd_procedures d
        ON p.icd_code = d.icd_code
        AND p.icd_version = d.icd_version
""").fetchone()

print(f"Total procedures:      {result[0]:,}")
print(f"Matched dictionary:    {result[1]:,}")
print(f"Unmatched:              {result[2]:,}")


print("\nExample procedure rows:")

rows = con.execute("""
    SELECT
        p.subject_id,
        p.hadm_id,
        p.chartdate,
        p.icd_code,
        p.icd_version,
        d.long_title
    FROM procedures_icd p
    LEFT JOIN d_icd_procedures d
        ON p.icd_code = d.icd_code
        AND p.icd_version = d.icd_version
    LIMIT 5
""").fetchall()

for row in rows:
    print(row)


# ---------------------------------------------------------
# CLOSE
# ---------------------------------------------------------

con.close()

print("\n" + "=" * 60)
print("JOIN TEST COMPLETE")
print("=" * 60)