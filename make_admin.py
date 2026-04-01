"""
Quick utility to promote a user to admin in the database.
Run: python make_admin.py your@email.com
"""
import sys
import os
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv()
DB_URI = os.getenv("DB_URI", "postgresql://postgres:0000@localhost:5432/colourizer")

def list_users():
    conn = psycopg2.connect(DB_URI)
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT id, email, name, role, is_admin FROM users ORDER BY id")
        users = cur.fetchall()
    conn.close()
    return users

def make_admin(email):
    conn = psycopg2.connect(DB_URI)
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT id, email, role FROM users WHERE email = %s", (email.lower(),))
        user = cur.fetchone()
        if not user:
            print(f"ERROR: No user found with email '{email}'")
            conn.close()
            return
        cur.execute(
            "UPDATE users SET role = 'admin', is_admin = TRUE WHERE id = %s",
            (user['id'],)
        )
    conn.commit()
    conn.close()
    print(f"SUCCESS: User '{email}' (ID={user['id']}) is now an ADMIN.")

if __name__ == '__main__':
    try:
        users = list_users()
        print("\n=== Current Users ===")
        for u in users:
            print(f"  ID={u['id']}  role={u['role']:<12} email={u['email']}")
        print()

        if len(sys.argv) < 2:
            if users:
                # Auto-promote the first user
                first = users[0]
                print(f"No email specified. Auto-promoting first user: {first['email']}")
                make_admin(first['email'])
            else:
                print("No users in database yet. Sign up first, then re-run this script.")
        else:
            email = sys.argv[1]
            make_admin(email)

    except Exception as e:
        print(f"ERROR: {e}")
        print("Make sure PostgreSQL is running and DB_URI in .env is correct.")
