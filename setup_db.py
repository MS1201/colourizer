import os
import psycopg2
from psycopg2 import sql

# Main DB URI used by the application
MAIN_DB_URI = os.getenv("DB_URI", "postgresql://postgres:0000@localhost:5432/colourizer")
# Admin DB URI (default postgres) for creating the target DB if it does not exist
ADMIN_DB_URI = os.getenv("ADMIN_DB_URI", "postgresql://postgres:0000@localhost:5432/postgres")


def ensure_database():
    conn = None
    try:
        # Connect to the admin database
        conn = psycopg2.connect(ADMIN_DB_URI)
        conn.autocommit = True
        cur = conn.cursor()
        db_name = "colourizer"
        cur.execute(sql.SQL("SELECT 1 FROM pg_database WHERE datname = %s"), [db_name])
        if not cur.fetchone():
            cur.execute(sql.SQL(f"CREATE DATABASE {sql.Identifier(db_name).string}"))
            print(f"Database '{db_name}' created.")
        else:
            print(f"Database '{db_name}' already exists.")
    except Exception as e:
        print("Error ensuring database:", e)
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    ensure_database()
    # After ensuring the DB exists, run the regular init_db to create tables
    import database
    # Override the DB_URI inside the database module to point to the correct DB
    database.DB_URI = MAIN_DB_URI
    database.init_db()


