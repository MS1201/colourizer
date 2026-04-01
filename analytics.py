"""
Analytics Module for Image Colorization
Tracks processing metrics and stores them in PostgreSQL (Supabase)
"""

import psycopg2
from psycopg2.extras import RealDictCursor
import os
from datetime import datetime
from contextlib import contextmanager
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Database connection string
DB_URI = os.getenv("DB_URI", os.getenv("DATABASE_URL", "postgresql://postgres:0000@localhost:5432/colourizer"))


@contextmanager
def get_db_connection():
    """Context manager for database connections"""
    conn = psycopg2.connect(DB_URI)
    try:
        yield conn
    finally:
        conn.close()


def init_database():
    """Initialize the analytics database with required tables"""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS colorization_logs (
                        id SERIAL PRIMARY KEY,
                        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        user_id INTEGER REFERENCES users(id),
                        original_filename TEXT,
                        image_width INTEGER,
                        image_height INTEGER,
                        file_size_kb REAL,
                        processing_time_seconds REAL,
                        quality_score REAL,
                        status TEXT,
                        error_message TEXT
                    )
                ''')
            # Commit the CREATE TABLE so it's not rolled back if the ALTER fails
            conn.commit()

            # Migration: Add user_id and filename columns if they don't exist
            with conn.cursor() as cursor:
                try:
                    cursor.execute('ALTER TABLE colorization_logs ADD COLUMN user_id INTEGER REFERENCES users(id)')
                    conn.commit()
                except psycopg2.Error:
                    conn.rollback()
                
                try:
                    cursor.execute('ALTER TABLE colorization_logs ADD COLUMN filename TEXT')
                    conn.commit()
                except psycopg2.Error:
                    conn.rollback()
    except psycopg2.OperationalError as e:
        print(f"⚠️ DATABASE WARNING: Could not connect to database during startup. Is DATABASE_URL set correctly? Continuing app boot... Error details: {e}")
    except Exception as e:
        print(f"⚠️ DATABASE ERROR: {e}")


def log_colorization(original_filename, filename, image_width, image_height, file_size_kb,
                     processing_time_seconds, quality_score, status, error_message=None, user_id=None):
    """Log a colorization attempt to the database"""
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute('''
                INSERT INTO colorization_logs 
                (original_filename, filename, image_width, image_height, file_size_kb,
                 processing_time_seconds, quality_score, status, error_message, user_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ''', (original_filename, filename, image_width, image_height, file_size_kb,
                  processing_time_seconds, quality_score, status, error_message, user_id))
        conn.commit()


def get_user_history(user_id):
    """Get colorization history for a specific user"""
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute('''
                SELECT 
                    timestamp,
                    original_filename,
                    filename,
                    image_width as width,
                    image_height as height,
                    status,
                    processing_time_seconds as processing_time,
                    quality_score
                FROM colorization_logs
                WHERE user_id = %s
                ORDER BY timestamp DESC
            ''', (user_id,))
            return [dict(row) for row in cursor.fetchall()]


def get_analytics_summary():
    """Get aggregated analytics summary"""
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            # Total images processed
            cursor.execute('SELECT COUNT(*) as count FROM colorization_logs')
            total = cursor.fetchone()['count']

            # Success count
            cursor.execute(
                'SELECT COUNT(*) as count FROM colorization_logs WHERE status = %s',
                ('success',)
            )
            success = cursor.fetchone()['count']

            # Average processing time for successful colorizations
            cursor.execute(
                'SELECT AVG(processing_time_seconds) as avg FROM colorization_logs WHERE status = %s',
                ('success',)
            )
            res = cursor.fetchone()
            avg_time = res['avg'] if res and res['avg'] is not None else 0

            # Average quality score
            cursor.execute(
                'SELECT AVG(quality_score) as avg FROM colorization_logs WHERE status = %s',
                ('success',)
            )
            res = cursor.fetchone()
            avg_quality = res['avg'] if res and res['avg'] is not None else 0

            # Total file size processed (in MB)
            cursor.execute(
                'SELECT SUM(file_size_kb) as total FROM colorization_logs WHERE status = %s',
                ('success',)
            )
            res = cursor.fetchone()
            total_size = res['total'] if res and res['total'] is not None else 0

            # Recent logs (last 10)
            cursor.execute('''
                SELECT timestamp, original_filename, image_width, image_height,
                       processing_time_seconds, quality_score, status
                FROM colorization_logs
                ORDER BY timestamp DESC
                LIMIT 10
            ''')
            recent = [dict(row) for row in cursor.fetchall()]

        return {
            'total_images': total,
            'successful_images': success,
            'failed_images': total - success,
            'success_rate': round((success / total * 100) if total > 0 else 0, 1),
            'avg_processing_time': round(float(avg_time), 2),
            'avg_quality_score': round(float(avg_quality), 1),
            'total_data_processed_mb': round(float(total_size) / 1024, 2),
            'recent_logs': recent
        }


def get_all_logs(limit=100):
    """Get all colorization logs for admin"""
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute('''
                SELECT * FROM colorization_logs
                ORDER BY timestamp DESC
                LIMIT %s
            ''', (limit,))
            return [dict(row) for row in cursor.fetchall()]


def get_global_stats():
    """Get global statistics for admin dashboard"""
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute('SELECT COUNT(*) as count FROM users')
            total_users = cursor.fetchone()['count']

            cursor.execute('SELECT COUNT(*) as count FROM colorization_logs')
            total_images = cursor.fetchone()['count']

            cursor.execute('SELECT COUNT(*) as count FROM colorization_logs WHERE status = \'success\'')
            success_count = cursor.fetchone()['count']

            cursor.execute('SELECT COUNT(*) as count FROM colorization_logs WHERE status = \'failed\'')
            failed_count = cursor.fetchone()['count']

    return {
        'total_users': total_users,
        'total_colorizations': total_images,
        'success_rate': round((success_count / total_images * 100) if total_images > 0 else 0, 1),
        'total_failed': failed_count
    }



# Initialize database on module import
init_database()
