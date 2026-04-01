"""
Authentication Module — Image Colorization App
Features:
  - RBAC (admin / moderator / user roles with granular permissions)
  - TOTP-based MFA via pyotp (free, no paid services)
  - Backup codes for MFA recovery
  - Session fingerprinting (IP + User-Agent hash)
  - CSRF token helpers
  - Rate limiting via DB
  - Password strength validation
  - Full audit logging
"""

import os
import re
import json
import random
import hashlib
import secrets
import psycopg2
import subprocess
from psycopg2.extras import RealDictCursor
from datetime import datetime, timedelta
from functools import wraps
from flask import session, redirect, url_for, request, jsonify, abort
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import LoginManager, UserMixin, current_user
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

try:
    import pyotp
    PYOTP_AVAILABLE = True
except ImportError:
    PYOTP_AVAILABLE = False

# ------------------------------------------------------------------
# Database
# ------------------------------------------------------------------
DB_URI = os.getenv("DB_URI", "postgresql://postgres:0000@localhost:5432/colourizer")

login_manager = LoginManager()


def get_db_connection():
    return psycopg2.connect(DB_URI)


# ------------------------------------------------------------------
# Email Utilities (Legacy / Still in Use)
# ------------------------------------------------------------------
def generate_otp():
    """Generate a 6-digit OTP"""
    return str(random.randint(100000, 999999))

def send_otp_email(user_email, otp):
    """Send OTP via Node.js nodemailer script"""
    return _send_via_node(user_email, otp)

def send_result_email(user_email, file_path):
    """Send colorized image via Node.js nodemailer script"""
    return _send_via_node(user_email, "RESULT", file_path)

def _send_via_node(user_email, otp_or_subject, file_path=None):
    """Internal helper to call the Node.js script"""
    sender_email = os.getenv("EMAIL_USER")
    sender_password = os.getenv("EMAIL_PASS")
    
    if not sender_email or not sender_password:
        print(f"\n{'='*60}")
        if file_path:
            print(f"🔒 MOCK EMAIL: Result for {user_email} (File: {file_path})")
        else:
            print(f"🔒 MOCK EMAIL: OTP for {user_email} is: {otp_or_subject}")
        print(f"⚠️  TO RECEIVE REAL EMAILS: Set EMAIL_USER/EMAIL_PASS in .env")
        print(f"{'='*60}\n")
        return True
        
    try:
        script_path = os.path.join(os.path.dirname(__file__), 'sendmail.js')
        args = ['node', script_path, user_email, otp_or_subject]
        if file_path: args.append(file_path)
            
        result = subprocess.run(args, capture_output=True, text=True, encoding='utf-8')
        if result.returncode == 0:
            return True
        return False
    except Exception as e:
        print(f"Exception calling sendmail.js: {e}")
        return False


# ------------------------------------------------------------------
# Permissions
# ------------------------------------------------------------------
ALL_PERMISSIONS = [
    "colorize",           # upload & colorize images
    "view_own_history",   # view own dashboard/history
    "view_all_logs",      # view all users' logs  (moderator+)
    "manage_users",       # ban/unban users        (admin)
    "delete_users",       # delete users           (admin)
    "change_roles",       # promote/demote roles   (admin)
    "view_admin_panel",   # access /admin          (admin, moderator)
    "view_security_logs", # view security/login logs (admin, moderator)
]

ROLE_PERMISSIONS = {
    "user": ["colorize", "view_own_history"],
    "moderator": ["colorize", "view_own_history", "view_all_logs",
                  "view_admin_panel", "view_security_logs"],
    "admin": ALL_PERMISSIONS,
}


def has_permission(user, permission: str) -> bool:
    """Check if a user (or role string) has a specific permission."""
    if user is None:
        return False
    role = getattr(user, "role", "user") or "user"
    return permission in ROLE_PERMISSIONS.get(role, [])


# ------------------------------------------------------------------
# Decorators
# ------------------------------------------------------------------
def permission_required(permission: str):
    """Route decorator — requires the logged-in user to have a permission."""
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for("login"))
            if not has_permission(current_user, permission):
                if request.path.startswith("/admin/api") or request.is_json:
                    return jsonify({"error": "Forbidden: insufficient permissions"}), 403
                return redirect(url_for("colorizer"))
            return f(*args, **kwargs)
        return decorated
    return decorator


def admin_required(f):
    """Convenience decorator — requires admin role."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for("login"))
        if not has_permission(current_user, "manage_users"):
            if request.path.startswith("/admin/api") or request.is_json:
                return jsonify({"error": "Forbidden: Admin access required"}), 403
            return redirect(url_for("colorizer"))
        return f(*args, **kwargs)
    return decorated


# ------------------------------------------------------------------
# User Model
# ------------------------------------------------------------------
class User(UserMixin):
    def __init__(self, id, email, name, created_at=None,
                 is_admin=False, is_banned=False, role="user",
                 mfa_enabled=False, mfa_secret=None, credits=100, plan="FREE"):
        self.id = id
        self.email = email
        self.name = name
        self.created_at = created_at
        self.is_admin = is_admin or (role == "admin")
        self.is_banned = is_banned
        self.role = role or ("admin" if is_admin else "user")
        self.mfa_enabled = mfa_enabled
        self.mfa_secret = mfa_secret
        self.credits = credits
        self.plan = plan

    def has_permission(self, permission: str) -> bool:
        return has_permission(self, permission)

    @staticmethod
    def _row_to_user(row):
        if not row:
            return None
        is_admin = row.get("is_admin", False)
        # Prioritize role column, fallback to is_admin check
        role = row.get("role") or ("admin" if is_admin else "user")
        
        return User(
            id=row["id"],
            email=row["email"],
            name=row["name"],
            created_at=row.get("created_at"),
            is_admin=is_admin,
            is_banned=row.get("is_banned", False),
            role=role,
            mfa_enabled=row.get("mfa_enabled", False),
            mfa_secret=row.get("mfa_secret"),
            credits=row.get("credits", 100),
            plan=row.get("plan", "FREE")
        )

    @staticmethod
    def get(user_id):
        conn = get_db_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM users WHERE id = %s", (user_id,))
                return User._row_to_user(cur.fetchone())
        finally:
            conn.close()

    @staticmethod
    def get_by_email(email):
        conn = get_db_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM users WHERE email = %s", (email.lower(),))
                return User._row_to_user(cur.fetchone())
        finally:
            conn.close()


@login_manager.user_loader
def load_user(user_id):
    return User.get(user_id)


# ------------------------------------------------------------------
# Database Init / Migrations
# ------------------------------------------------------------------
def init_db():
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            # Users table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    email TEXT UNIQUE NOT NULL,
                    name TEXT NOT NULL,
                    password_hash TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    credits INTEGER DEFAULT 100,
                    plan TEXT DEFAULT 'FREE',
                    is_admin BOOLEAN DEFAULT FALSE,
                    is_banned BOOLEAN DEFAULT FALSE,
                    role TEXT DEFAULT 'user',
                    mfa_enabled BOOLEAN DEFAULT FALSE,
                    mfa_secret TEXT,
                    backup_codes TEXT
                )
            """)

            # Login attempts (rate limiting + security log)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS login_attempts (
                    id SERIAL PRIMARY KEY,
                    ip_address TEXT NOT NULL,
                    email TEXT,
                    attempted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    success INTEGER DEFAULT 0,
                    mfa_attempt BOOLEAN DEFAULT FALSE
                )
            """)

            # Admin audit log
            cur.execute("""
                CREATE TABLE IF NOT EXISTS admin_actions (
                    id SERIAL PRIMARY KEY,
                    admin_id INTEGER REFERENCES users(id),
                    action TEXT NOT NULL,
                    target_user_id INTEGER,
                    details TEXT,
                    performed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # History table (Still used in app.py)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS history (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER REFERENCES users(id),
                    original_filename TEXT,
                    filename TEXT,
                    width INTEGER,
                    height INTEGER,
                    processing_time REAL,
                    quality_score REAL,
                    status TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Migrations — safe ADD COLUMN IF NOT EXISTS
            migrations = [
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS credits INTEGER DEFAULT 100",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS plan TEXT DEFAULT 'FREE'",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_admin BOOLEAN DEFAULT FALSE",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_banned BOOLEAN DEFAULT FALSE",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS role TEXT DEFAULT 'user'",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS mfa_enabled BOOLEAN DEFAULT FALSE",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS mfa_secret TEXT",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS backup_codes TEXT",
                "ALTER TABLE login_attempts ADD COLUMN IF NOT EXISTS mfa_attempt BOOLEAN DEFAULT FALSE",
            ]
            for sql in migrations:
                try:
                    cur.execute(sql)
                except Exception:
                    conn.rollback()

            # Sync role field with is_admin for existing rows
            cur.execute("""
                UPDATE users SET role = 'admin'
                WHERE is_admin = TRUE AND (role IS NULL OR role = 'user')
            """)

        conn.commit()
    finally:
        conn.close()


# ------------------------------------------------------------------
# CSRF
# ------------------------------------------------------------------
def generate_csrf_token() -> str:
    """Generate a CSRF token and store it in the session."""
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_hex(32)
    return session["csrf_token"]


def validate_csrf_token() -> bool:
    """Validate the CSRF token from form/header against session."""
    token = request.form.get("csrf_token")
    if not token:
        token = request.headers.get("X-CSRF-Token")
    if not token and request.is_json:
        try:
            token = request.get_json(silent=True, force=True).get("csrf_token")
        except Exception:
            token = None
    expected = session.get("csrf_token")
    return bool(token and expected and token == expected)


# ------------------------------------------------------------------
# Session Fingerprinting
# ------------------------------------------------------------------
def create_session_fingerprint() -> str:
    """Create a fingerprint from IP + User-Agent."""
    ip = request.headers.get("X-Forwarded-For", request.remote_addr).split(",")[0].strip()
    ua = request.headers.get("User-Agent", "")
    raw = f"{ip}|{ua}"
    return hashlib.sha256(raw.encode()).hexdigest()


def store_session_fingerprint():
    session["_fp"] = create_session_fingerprint()


def validate_session_fingerprint() -> bool:
    """Returns True if fingerprint matches or not yet set."""
    stored = session.get("_fp")
    if not stored:
        return True  # Not yet set — first request after login
    return stored == create_session_fingerprint()


# ------------------------------------------------------------------
# CAPTCHA
# ------------------------------------------------------------------
def generate_captcha() -> str:
    num1 = random.randint(1, 20)
    num2 = random.randint(1, 20)
    ops = ["+", "-", "×"]
    op = random.choice(ops)
    if op == "+":
        answer, question = num1 + num2, f"{num1} + {num2}"
    elif op == "-":
        if num1 < num2: num1, num2 = num2, num1
        answer, question = num1 - num2, f"{num1} - {num2}"
    else:
        num1, num2 = random.randint(1, 10), random.randint(1, 10)
        answer, question = num1 * num2, f"{num1} × {num2}"
    session["captcha_answer"] = str(answer)
    session["captcha_timestamp"] = datetime.now().isoformat()
    return question


def verify_captcha(user_answer: str) -> bool:
    if "captcha_answer" not in session: return False
    try:
        ts = datetime.fromisoformat(session.get("captcha_timestamp", ""))
        if datetime.now() - ts > timedelta(minutes=5): return False
    except Exception: return False
    correct = session.get("captcha_answer", "")
    session.pop("captcha_answer", None)
    session.pop("captcha_timestamp", None)
    return str(user_answer).strip() == correct


# ------------------------------------------------------------------
# Validation
# ------------------------------------------------------------------
def validate_email(email: str) -> bool:
    return bool(re.match(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$", email))


def validate_password(password: str):
    if len(password) < 8: return False, "Password must be at least 8 characters"
    if not re.search(r"[A-Z]", password): return False, "Password must contain an uppercase letter"
    if not re.search(r"[a-z]", password): return False, "Password must contain a lowercase letter"
    if not re.search(r"\d", password): return False, "Password must contain a number"
    return True, None


def get_password_strength(password: str) -> int:
    score = 0
    length = len(password)
    if length >= 8:  score += 20
    if length >= 12: score += 10
    if length >= 16: score += 10
    if re.search(r"[a-z]", password): score += 15
    if re.search(r"[A-Z]", password): score += 15
    if re.search(r"\d", password):    score += 15
    if re.search(r'[!@#$%^&*(),.?":{}|<>]', password): score += 15
    return min(score, 100)


# ------------------------------------------------------------------
# Rate Limiting
# ------------------------------------------------------------------
def check_rate_limit(ip_address: str, max_attempts=5, window_minutes=15):
    conn = get_db_connection()
    window_start = datetime.now() - timedelta(minutes=window_minutes)
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT COUNT(*) AS count FROM login_attempts
                WHERE ip_address = %s AND attempted_at > %s AND success = 0
            """, (ip_address, window_start))
            failed = (cur.fetchone() or {}).get("count", 0)
    finally:
        conn.close()
    remaining = max(0, max_attempts - failed)
    if failed >= max_attempts:
        return False, 0, window_minutes
    return True, remaining, 0


def log_login_attempt(ip_address: str, email: str, success: bool, mfa_attempt=False):
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO login_attempts (ip_address, email, success, mfa_attempt)
                VALUES (%s, %s, %s, %s)
            """, (ip_address, email, 1 if success else 0, mfa_attempt))
        conn.commit()
    finally:
        conn.close()


def clear_failed_attempts(ip_address: str):
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM login_attempts WHERE ip_address = %s AND success = 0",
                        (ip_address,))
        conn.commit()
    finally:
        conn.close()


# ------------------------------------------------------------------
# MFA (TOTP via pyotp)
# ------------------------------------------------------------------
def generate_mfa_secret() -> str:
    """Generate a new TOTP secret (base32)."""
    if not PYOTP_AVAILABLE:
        raise RuntimeError("pyotp is not installed. Run: pip install pyotp")
    return pyotp.random_base32()


def get_totp_uri(secret: str, email: str, issuer: str = "ImageColorizer") -> str:
    """Return the otpauth:// URI for QR code generation."""
    totp = pyotp.TOTP(secret)
    return totp.provisioning_uri(name=email, issuer_name=issuer)


def verify_totp(secret: str, code: str) -> bool:
    """Verify a TOTP code against a secret (allows 1 window drift)."""
    if not PYOTP_AVAILABLE or not secret or not code: return False
    totp = pyotp.TOTP(secret)
    return totp.verify(str(code).strip(), valid_window=1)


def generate_backup_codes(count=8) -> list[str]:
    """Generate one-time backup codes."""
    return [secrets.token_hex(4).upper() for _ in range(count)]


def enable_mfa(user_id: int, secret: str) -> tuple:
    """Enable MFA for a user. Generate and store backup codes."""
    backup_codes = generate_backup_codes()
    hashed_codes = [hashlib.sha256(c.encode()).hexdigest() for c in backup_codes]
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE users
                SET mfa_enabled = TRUE, mfa_secret = %s, backup_codes = %s
                WHERE id = %s
            """, (secret, json.dumps(hashed_codes), user_id))
        conn.commit()
    finally:
        conn.close()
    return backup_codes


def disable_mfa(user_id: int):
    """Disable MFA and clear secret/backup codes."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE users
                SET mfa_enabled = FALSE, mfa_secret = NULL, backup_codes = NULL
                WHERE id = %s
            """, (user_id,))
        conn.commit()
    finally:
        conn.close()


def verify_backup_code(user_id: int, code: str) -> bool:
    """Verify and consume a backup code (one-time use)."""
    code = code.strip().upper()
    code_hash = hashlib.sha256(code.encode()).hexdigest()
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT backup_codes FROM users WHERE id = %s", (user_id,))
            row = cur.fetchone()
            if not row or not row.get("backup_codes"): return False
            codes = json.loads(row["backup_codes"])
            if code_hash not in codes: return False
            codes.remove(code_hash)
            cur.execute("UPDATE users SET backup_codes = %s WHERE id = %s",
                        (json.dumps(codes), user_id))
        conn.commit()
        return True
    except Exception: return False
    finally: conn.close()


# ------------------------------------------------------------------
# User CRUD
# ------------------------------------------------------------------
def create_user(email: str, name: str, password: str):
    email = email.lower().strip()
    name = name.strip()
    if not validate_email(email): return False, "Invalid email format"
    valid, err = validate_password(password)
    if not valid: return False, err
    if User.get_by_email(email): return False, "Email already registered"
    password_hash = generate_password_hash(password, method="pbkdf2:sha256", salt_length=16)
    try:
        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                # Check for first user
                cur.execute("SELECT COUNT(*) FROM users")
                is_first = (cur.fetchone()[0] == 0)
                role = "admin" if is_first else "user"
                is_admin = is_first

                cur.execute("""
                    INSERT INTO users (email, name, password_hash, role, is_admin)
                    VALUES (%s, %s, %s, %s, %s) RETURNING id
                """, (email, name, password_hash, role, is_admin))
                user_id = cur.fetchone()[0]
            conn.commit()
        finally:
            conn.close()
        return True, User(id=user_id, email=email, name=name, role=role, is_admin=is_admin)
    except psycopg2.IntegrityError: return False, "Email already registered"
    except Exception as e: return False, str(e)


def authenticate_user(email: str, password: str):
    email = email.lower().strip()
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM users WHERE email = %s", (email,))
            row = cur.fetchone()
    finally:
        conn.close()
    if not row: return False, "Invalid email or password"
    if row.get("is_banned"): return False, "Your account has been suspended."
    if not check_password_hash(row["password_hash"], password): return False, "Invalid email or password"
    return True, User._row_to_user(row)


def change_password(user_id: int, old_password: str, new_password: str):
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT password_hash FROM users WHERE id = %s", (user_id,))
            row = cur.fetchone()
        if not row: return False, "User not found"
        if not check_password_hash(row["password_hash"], old_password): return False, "Current password incorrect"
        valid, err = validate_password(new_password)
        if not valid: return False, err
        new_hash = generate_password_hash(new_password, method="pbkdf2:sha256", salt_length=16)
        with conn.cursor() as cur:
            cur.execute("UPDATE users SET password_hash = %s WHERE id = %s", (new_hash, user_id))
        conn.commit()
        return True, None
    finally: conn.close()


# ------------------------------------------------------------------
# Admin Operations
# ------------------------------------------------------------------
def get_all_users():
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT
                    u.id, u.email, u.name, u.created_at, u.is_admin, u.is_banned,
                    u.role, u.mfa_enabled, u.credits, u.plan,
                    COUNT(cl.id) AS total_images,
                    MAX(cl.timestamp) AS last_activity
                FROM users u
                LEFT JOIN colorization_logs cl ON cl.user_id = u.id
                GROUP BY u.id, u.email, u.name, u.created_at, u.is_admin,
                         u.is_banned, u.role, u.mfa_enabled, u.credits, u.plan
                ORDER BY u.created_at DESC
            """)
            return [dict(row) for row in cur.fetchall()]
    finally: conn.close()


def toggle_user_ban(user_id: int):
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT is_banned FROM users WHERE id = %s", (user_id,))
            row = cur.fetchone()
            if not row: return None, "User not found"
            new_state = not row["is_banned"]
            cur.execute("UPDATE users SET is_banned = %s WHERE id = %s", (new_state, user_id))
        conn.commit()
        return new_state, None
    finally: conn.close()


def change_user_role(user_id: int, new_role: str):
    if new_role not in ROLE_PERMISSIONS: return False, "Invalid role"
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE users SET role = %s, is_admin = %s WHERE id = %s", (new_role, new_role == "admin", user_id))
        conn.commit()
        return True, None
    except Exception as e: return False, str(e)
    finally: conn.close()


def delete_user_by_id(user_id: int):
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM users WHERE id = %s", (user_id,))
        conn.commit()
        return True, None
    except Exception as e: return False, str(e)
    finally: conn.close()


def log_admin_action(admin_id: int, action: str, target_user_id=None, details=None):
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO admin_actions (admin_id, action, target_user_id, details)
                VALUES (%s, %s, %s, %s)
            """, (admin_id, action, target_user_id, details))
        conn.commit()
    except Exception: pass
    finally: conn.close()


def get_recent_login_attempts(limit=100):
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT ip_address, email, attempted_at, success, mfa_attempt
                FROM login_attempts
                ORDER BY attempted_at DESC
                LIMIT %s
            """, (limit,))
            return [dict(row) for row in cur.fetchall()]
    finally: conn.close()


def get_all_roles():
    return [{"name": role, "permissions": perms} for role, perms in ROLE_PERMISSIONS.items()]


# Initialize DB on import
init_db()
