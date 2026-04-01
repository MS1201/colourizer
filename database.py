"""
Database Module for Image Colorization App
PostgreSQL (Supabase) backend — replaces SQLite
"""

import os
import psycopg2
from psycopg2.extras import RealDictCursor
DB_URI = os.getenv("DB_URI", "postgresql://postgres:0000@localhost:5432/colourizer")

# Database connection string
# Password 'Dhruvil-@11' is URL encoded to 'Dhruvil-%4011' to handle the '@' symbol


def get_db_connection():
    """Return a psycopg2 connection with RealDictCursor as row_factory equivalent"""
    conn = psycopg2.connect(DB_URI)
    return conn


def init_db():
    """Initialize all required tables"""
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # Users table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    email TEXT UNIQUE NOT NULL,
                    name TEXT NOT NULL,
                    password_hash TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    credits INTEGER DEFAULT 100,
                    plan TEXT DEFAULT 'FREE'
                )
            ''')

            # History table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS history (
                    id SERIAL PRIMARY KEY,
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

        conn.commit()
    finally:
        conn.close()


if __name__ == '__main__':
    init_db()
    print("PostgreSQL database initialized successfully.")
