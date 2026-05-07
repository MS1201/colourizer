"""
Database Module for Image Colorization App
Supports PostgreSQL and SQLite fallback.
"""

import os
import sqlite3
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv
from contextlib import contextmanager

load_dotenv()

DB_URI = os.getenv("DB_URI", os.getenv("DATABASE_URL"))
IS_POSTGRES = DB_URI and (DB_URI.startswith("postgresql://") or DB_URI.startswith("postgres://"))

def get_db_connection():
    """Return a database connection. Fallback to SQLite if Postgres is unavailable."""
    global IS_POSTGRES
    
    if IS_POSTGRES:
        try:
            conn = psycopg2.connect(DB_URI)
            return conn
        except Exception as e:
            print(f"⚠️ POSTGRES ERROR: {e}. Falling back to SQLite.")
            IS_POSTGRES = False

    # SQLite fallback
    db_path = os.getenv("SQLITE_DB_PATH", "app.db")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

class CursorWrapper:
    def __init__(self, cursor, is_postgres):
        self.cursor = cursor
        self.is_postgres = is_postgres
    
    def execute(self, query, vars=None):
        if not self.is_postgres:
            query = query.replace("%s", "?")
            if " RETURNING id" in query:
                self._returning_id = True
                query = query.replace(" RETURNING id", "")
            else:
                self._returning_id = False
        
        if vars is None:
            return self.cursor.execute(query)
        return self.cursor.execute(query, vars)
    
    def fetchone(self):
        if not self.is_postgres and getattr(self, '_returning_id', False):
            self._returning_id = False
            return (self.cursor.lastrowid,)
        row = self.cursor.fetchone()
        if row and not self.is_postgres:
            return dict(row)
        return row

    def fetchall(self):
        rows = self.cursor.fetchall()
        if rows and not self.is_postgres:
            return [dict(r) for r in rows]
        return rows

    def executemany(self, query, vars_list):
        if not self.is_postgres:
            query = query.replace("%s", "?")
        return self.cursor.executemany(query, vars_list)

    def __getattr__(self, name):
        return getattr(self.cursor, name)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.cursor.close()

@contextmanager
def get_db_cursor(conn):
    """Context manager for a dictionary-like cursor that handles placeholder differences."""
    if IS_POSTGRES:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
    else:
        cursor = conn.cursor()
    
    wrapper = CursorWrapper(cursor, IS_POSTGRES)
    try:
        yield wrapper
    finally:
        if IS_POSTGRES: # wrapper doesn't close it, we do it here if not using wrapper's __exit__
            cursor.close()

def init_db():
    """Initialize all required tables"""
    conn = get_db_connection()
    try:
        with get_db_cursor(conn) as cursor:
            id_type = "SERIAL PRIMARY KEY" if IS_POSTGRES else "INTEGER PRIMARY KEY AUTOINCREMENT"
            
            # Users table
            cursor.execute(f'''
                CREATE TABLE IF NOT EXISTS users (
                    id {id_type},
                    email TEXT UNIQUE NOT NULL,
                    name TEXT NOT NULL,
                    password_hash TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    credits INTEGER DEFAULT 100,
                    plan TEXT DEFAULT 'FREE',
                    mfa_enabled BOOLEAN DEFAULT FALSE,
                    mfa_secret TEXT,
                    role TEXT DEFAULT 'user',
                    is_banned BOOLEAN DEFAULT FALSE,
                    is_admin BOOLEAN DEFAULT FALSE,
                    backup_codes TEXT
                )
            ''')

            # History table (also used as colorization_logs)
            cursor.execute(f'''
                CREATE TABLE IF NOT EXISTS history (
                    id {id_type},
                    user_id INTEGER NOT NULL REFERENCES users(id),
                    original_filename TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    width INTEGER,
                    height INTEGER,
                    processing_time REAL,
                    quality_score REAL,
                    status TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Colorization logs table (legacy alias)
            cursor.execute(f'''
                CREATE TABLE IF NOT EXISTS colorization_logs (
                    id {id_type},
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    user_id INTEGER REFERENCES users(id),
                    original_filename TEXT,
                    filename TEXT,
                    image_width INTEGER,
                    image_height INTEGER,
                    file_size_kb REAL,
                    processing_time_seconds REAL,
                    quality_score REAL,
                    status TEXT,
                    error_message TEXT
                )
            ''')

            # Login attempts table
            cursor.execute(f'''
                CREATE TABLE IF NOT EXISTS login_attempts (
                    id {id_type},
                    ip_address TEXT NOT NULL,
                    email TEXT,
                    attempted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    success INTEGER DEFAULT 0,
                    mfa_attempt BOOLEAN DEFAULT FALSE
                )
            ''')

            # Admin actions table
            cursor.execute(f'''
                CREATE TABLE IF NOT EXISTS admin_actions (
                    id {id_type},
                    admin_id INTEGER REFERENCES users(id),
                    action TEXT NOT NULL,
                    target_user_id INTEGER,
                    details TEXT,
                    performed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Seed admin user
            ADMIN_EMAIL = "ms9409621877@gmail.com"
            ADMIN_PASS = "Admin@1234"
            cursor.execute("SELECT COUNT(*) as count FROM users WHERE email = %s", (ADMIN_EMAIL,))
            count = cursor.fetchone()
            # Handle both dict and tuple returns from wrapper
            count_val = count['count'] if isinstance(count, dict) else count[0]
            
            if count_val == 0:
                from werkzeug.security import generate_password_hash
                password_hash = generate_password_hash(ADMIN_PASS, method="pbkdf2:sha256", salt_length=16)
                cursor.execute("""
                    INSERT INTO users (email, name, password_hash, role, is_admin)
                    VALUES (%s, %s, %s, %s, %s)
                """, (ADMIN_EMAIL, "Admin", password_hash, "admin", True))
            
        conn.commit()
    except Exception as e:
        print(f"⚠️ DATABASE ERROR during init: {e}")
    finally:
        conn.close()

if __name__ == '__main__':
    init_db()
    print("Database initialized successfully.")


if __name__ == '__main__':
    init_db()
    print("Database initialized successfully.")


