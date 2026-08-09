import duckdb

con = duckdb.connect("database/mimic.duckdb", read_only=True)

# Check 1: What lab items are available?
print("=== AVAILABLE LAB ITEMS ===")
lab_items = con.execute("SELECT DISTINCT LOWER(label) FROM d_labitems WHERE label LIKE '%sodium%' OR label LIKE '%glucose%' OR label LIKE '%creatinine%'").fetchall()
print("Lab items containing key words:", lab_items)
print()

# Check 2: What chart items are available?
print("=== AVAILABLE CHART ITEMS ===")
chart_items = con.execute("SELECT DISTINCT LOWER(label) FROM d_items WHERE label LIKE '%sodium%' OR label LIKE '%glucose%' LIMIT 10").fetchall()
print("Chart items:", chart_items)
print()

# Check 3: Check for specific subject Q001
print("=== CHECKING Q001 (subject 10002428, stay 35479615) ===")
subject_id = 10002428
stay_id = 35479615
hadm_id = 23473524

sodium_in_labs = con.execute(
    "SELECT COUNT(*) FROM labevents l JOIN d_labitems d ON l.itemid = d.itemid WHERE l.subject_id = ? AND LOWER(d.label) LIKE '%sodium%'",
    [subject_id]
).fetchone()
print(f"Sodium records in labevents for subject {subject_id}: {sodium_in_labs[0]}")

# Check if sodium exists at all
sodium_itemids = con.execute("SELECT itemid, label FROM d_labitems WHERE LOWER(label) LIKE '%sodium%'").fetchall()
print(f"Sodium itemids: {sodium_itemids}")
print()

# Check 4: Glucose issue - why returning None?
print("=== CHECKING GLUCOSE (Q021) ===")
subject_id = 10040025
hadm_id = 23514019
glucose = con.execute("""
    SELECT l.charttime, l.valuenum, l.value, d.label
    FROM labevents l
    JOIN d_labitems d ON l.itemid = d.itemid
    WHERE l.subject_id = ? AND l.hadm_id = ? AND LOWER(d.label) LIKE '%glucose%'
    ORDER BY l.charttime
    LIMIT 1
""", [subject_id, hadm_id]).fetchall()
print(f"First glucose for Q021: {glucose}")
print()

# Check 5: Event count issue - chartevents vs labevents
print("=== EVENT COUNT DISTINCTION ===")
subject_id = 10040025
stay_id = 35479644
chartevents_count = con.execute(
    "SELECT COUNT(*) FROM chartevents WHERE subject_id = ? AND stay_id = ?",
    [subject_id, stay_id]
).fetchone()[0]
labevents_count = con.execute(
    "SELECT COUNT(*) FROM labevents WHERE subject_id = ? AND hadm_id = (SELECT hadm_id FROM icustays WHERE stay_id = ?)",
    [subject_id, stay_id]
).fetchone()[0]
print(f"Chart events: {chartevents_count}")
print(f"Lab events: {labevents_count}")

con.close()
