import os
import psycopg2

db_uri = os.getenv("DB_URI", "postgresql://postgres:0000@localhost:5432/colourizer")
conn = psycopg2.connect(db_uri)
cur = conn.cursor()
cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")
tables = cur.fetchall()
print("Tables in colourizer database:", tables)
cur.close()
conn.close()
