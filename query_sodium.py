# import duckdb

# con = duckdb.connect("database/mimic.duckdb")

# # Run your query with a subject_id parameter
# # Change the subject_id value as needed
# subject_id = 10001  # Example subject ID

# result = con.execute("""
# SELECT
#     l.charttime,
#     l.itemid,
#     l.valuenum,
#     l.value,
#     d.label
# FROM labevents l
# JOIN d_labitems d
#     ON l.itemid = d.itemid
# WHERE l.subject_id = ?
#   AND LOWER(d.label) LIKE '%sodium%'
# ORDER BY l.charttime
# LIMIT 20;
# """, [subject_id]).fetchdf()

# print(result)
# con.close()

import duckdb

con = duckdb.connect("database/mimic.duckdb", read_only=True)

result = con.execute("""
SELECT
    l.charttime,
    l.itemid,
    l.valuenum,
    l.value,
    d.label
FROM labevents l
JOIN d_labitems d
    ON l.itemid = d.itemid
JOIN icustays i
    ON l.subject_id = i.subject_id
    AND l.hadm_id = i.hadm_id
WHERE l.subject_id = ?
  AND l.hadm_id = ?
  AND i.stay_id = ?
  AND LOWER(d.label) LIKE '%sodium%'
  AND l.charttime >= i.intime
  AND l.charttime <= i.outtime
ORDER BY l.charttime
LIMIT 20;
""", [10002428, 23473524, 35479615]).fetchdf()

print(result)
con.close()