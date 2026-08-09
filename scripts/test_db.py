import duckdb

con = duckdb.connect("database/mimic.duckdb")

# print(con.execute("SHOW TABLES").fetchall())

# con.close()

result = con.execute("""
    SELECT *
    FROM patients
    LIMIT 5
""").fetchdf()

print(result)