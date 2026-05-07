"""
Flask Application for Image Colorization with Analytics
Now with RBAC, MFA (TOTP), Session Security, and Anti-CSRF
"""

import os
import time
import uuid
import base64
import cv2
import gc
import requests
import hashlib
from io import BytesIO
from flask import (Flask, render_template, request, jsonify, send_file,
                   redirect, url_for, session, make_response, flash)
from werkzeug.utils import secure_filename
from flask_login import login_required, login_user, logout_user, current_user
from dotenv import load_dotenv
from PIL import Image as PilImage
import base64

# Load environment variables
load_dotenv()

# Attempt to load pyotp and qrcode for MFA
try:
    import pyotp
    PYOTP_AVAILABLE = True
except ImportError:
    PYOTP_AVAILABLE = False

try:
    import qrcode
    from PIL import Image
    QR_AVAILABLE = True
except ImportError:
    QR_AVAILABLE = False

from colorizer import colorize_image, get_colorizer
from analytics import log_colorization, get_analytics_summary, get_user_history, get_all_logs, get_global_stats
from auth import (
    login_manager, User, create_user, authenticate_user, change_password,
    generate_captcha, verify_captcha, check_rate_limit, log_login_attempt, clear_failed_attempts,
    admin_required, permission_required, has_permission, get_all_users, toggle_user_ban,
    change_user_role, delete_user_by_id, log_admin_action, get_recent_login_attempts, get_all_roles,
    generate_csrf_token, validate_csrf_token,
    create_session_fingerprint, store_session_fingerprint, validate_session_fingerprint,
    generate_mfa_secret, get_totp_uri, verify_totp, enable_mfa, disable_mfa, verify_backup_code,
    send_otp_email, send_result_email, generate_otp
)
from database import get_db_connection, get_db_cursor

# Configuration - Using existing project paths
UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'static', 'uploads')
COLORIZED_FOLDER = os.path.join(os.path.dirname(__file__), 'static', 'results')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'bmp', 'webp'}

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(COLORIZED_FOLDER, exist_ok=True)

# Initialize Flask app
app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
# Lowered from 500MB to 100MB for Render Free tier stability. 
# 100MB is safe for high-res JPEGs when using cloud storage fallback.
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  
app.config['SECRET_KEY'] = os.getenv("SECRET_KEY", "dev_secret_key_change_in_production_12345")

# Cloudinary Setup (for "unlimited" cloud storage)
import cloudinary
import cloudinary.uploader
if os.getenv("CLOUDINARY_URL"):
    cloudinary.config(cloudinary_url=os.getenv("CLOUDINARY_URL"))
    HAS_CLOUDINARY = True
else:
    HAS_CLOUDINARY = False

# Initialize Flask-Login
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Please log in to access this page.'


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def get_client_ip():
    if request.headers.get('X-Forwarded-For'):
        return request.headers.get('X-Forwarded-For').split(',')[0].strip()
    return request.remote_addr


def cleanup_storage(max_age_seconds=600):
    """
    Delete files older than max_age_seconds to free up disk space.
    Critical for Render Free Tier which has limited ephemeral storage.
    """
    folders_to_clean = [UPLOAD_FOLDER]
    if HAS_CLOUDINARY:
        folders_to_clean.append(COLORIZED_FOLDER)
        
    for folder in folders_to_clean:
        try:
            if not os.path.exists(folder):
                continue
            now = time.time()
            for filename in os.listdir(folder):
                file_path = os.path.join(folder, filename)
                if filename.startswith('.'):
                    continue
                if os.path.isfile(file_path):
                    if now - os.path.getmtime(file_path) > max_age_seconds:
                        try:
                            os.remove(file_path)
                        except OSError:
                            pass
        except Exception as e:
            print(f"Cleanup error: {e}")

def safe_isoformat(dt):
    """Helper to safely call isoformat on datetime objects or strings."""
    if hasattr(dt, 'isoformat'):
        return dt.isoformat()
    return str(dt)

def check_image_security(file_stream):
    """
    Security scan bypass - Always returns clean as requested.
    """
    return True, None


# ============== MIDDLEWARE (SECURITY) ==============

@app.before_request
def security_checks():
    """Execute security checks before processing any route."""
    # 1. Provide CSRF token for all templates
    app.jinja_env.globals['csrf_token'] = generate_csrf_token
    app.jinja_env.globals['has_permission'] = has_permission

    # 2. Check CSRF on state-changing requests
    if request.method in ["POST", "PUT", "DELETE", "PATCH"]:
        if not validate_csrf_token():
            if request.is_json or request.path == "/upload":
                return jsonify({"error": "Invalid CSRF token. Please refresh the page."}), 400
            error = "Session expired or invalid form submission. Please try again."
            if request.endpoint == "login":
                return render_template("login.html", error=error, captcha_question=generate_captcha())
            if request.endpoint == "signup":
                return render_template("signup.html", error=error, captcha_question=generate_captcha())
            return jsonify({"error": "Invalid CSRF token"}), 400

    # 3. Session Fingerprinting
    if current_user.is_authenticated:
        if not validate_session_fingerprint():
            logout_user()
            if request.is_json or request.path == "/upload":
                return jsonify({"error": "Session hijacked or network changed."}), 401
            return redirect(url_for("login", error="Session hijacked or network changed."))

@app.errorhandler(413)
def request_entity_too_large(error):
    return jsonify({"error": "File too large. Your server or proxy has a size limit — please contact the administrator."}), 413


@app.after_request
def add_security_headers(response):
    """Add modern HTTP security headers to all responses."""
    headers = {
        'X-Content-Type-Options': 'nosniff',
        'X-Frame-Options': 'DENY',
        'X-XSS-Protection': '1; mode=block',
        'Strict-Transport-Security': 'max-age=31536000; includeSubDomains',
        'Referrer-Policy': 'strict-origin-when-cross-origin',
        'Content-Security-Policy': (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' data: https://fonts.gstatic.com; "
            "img-src 'self' data: blob: https://res.cloudinary.com; "
            "connect-src 'self'"
        )
    }
    for key, val in headers.items():
        if key not in response.headers:
            response.headers[key] = val
    return response


# ============== AUTHENTICATION ROUTES ==============

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('colorizer'))

    error = request.args.get('error')
    success = request.args.get('success')

    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        captcha_answer = request.form.get('captcha', '')
        remember = request.form.get('remember') == '1'

        client_ip = get_client_ip()

        is_allowed, remaining, lockout_mins = check_rate_limit(client_ip)
        if not is_allowed:
            error = f'Too many failed attempts. Please try again in {lockout_mins} minutes.'
            return render_template('login.html', error=error, captcha_question=generate_captcha())

        if not verify_captcha(captcha_answer):
            error = 'Incorrect security answer. Please try again.'
            log_login_attempt(client_ip, email, False)
            return render_template('login.html', error=error, captcha_question=generate_captcha())

        success_auth, result = authenticate_user(email, password)

        if success_auth:
            user = result
            # MFA Check (TOTP App)
            if user.mfa_enabled:
                session['pre_mfa_user_id'] = user.id
                session['pre_mfa_remember'] = remember
                return redirect(url_for('mfa_challenge'))

            # No MFA enabled, login directly
            login_user(user, remember=remember)
            store_session_fingerprint()
            clear_failed_attempts(client_ip)
            log_login_attempt(client_ip, user.email, True)

            next_page = request.args.get('next')
            if next_page:
                return redirect(next_page)
            if user.role == 'admin':
                return redirect(url_for('admin_dashboard'))
            return redirect(url_for('colorizer'))
        else:
            error = result
            log_login_attempt(client_ip, email, False)

    return render_template('login.html', error=error, success=success, captcha_question=generate_captcha())


@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for('colorizer'))

    error = None
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        captcha_answer = request.form.get('captcha', '')
        terms = request.form.get('terms')

        if not terms:
            error = 'You must accept the Terms of Service.'
            return render_template('signup.html', error=error, captcha_question=generate_captcha())

        if not verify_captcha(captcha_answer):
            error = 'Incorrect security answer. Please try again.'
            return render_template('signup.html', error=error, captcha_question=generate_captcha())

        if len(name) < 2:
            error = 'Please enter your full name.'
            return render_template('signup.html', error=error, captcha_question=generate_captcha())

        if password != confirm_password:
            error = 'Passwords do not match.'
            return render_template('signup.html', error=error, captcha_question=generate_captcha())

        success, result = create_user(email, name, password)

        if success:
            return redirect(url_for('login', success='Account created successfully! Please log in.'))
        else:
            error = result

    return render_template('signup.html', error=error, captcha_question=generate_captcha())


@app.route('/logout', methods=['GET', 'POST'])
@login_required
def logout():
    logout_user()
    session.clear()
    return redirect(url_for('landing'))


@app.route('/verify_otp', methods=['GET', 'POST'])
def verify_otp():
    """Verify Email OTP."""
    if current_user.is_authenticated:
        return redirect(url_for('colorizer'))
        
    if 'pending_user_id' not in session or 'pending_otp' not in session:
        return redirect(url_for('login'))
        
    error = None
    if request.method == 'POST':
        user_otp = request.form.get('otp', '').strip()
        if user_otp == session.get('pending_otp'):
            user_id = session.pop('pending_user_id')
            session.pop('pending_otp')
            remember = session.pop('pending_remember', False)
            next_page = session.pop('pending_next', None)
            client_ip = session.pop('pending_client_ip', get_client_ip())
            email = session.pop('pending_email', '')
            
            user = User.get(user_id)
            if user:
                login_user(user, remember=remember)
                store_session_fingerprint()
                clear_failed_attempts(client_ip)
                log_login_attempt(client_ip, email, True)
                
                return redirect(next_page) if next_page else redirect(url_for('colorizer'))
            else:
                return redirect(url_for('login'))
        else:
            error = "Invalid OTP. Please try again."
            
    return render_template('verify_otp.html', error=error)


@app.route('/resend_otp')
def resend_otp():
    """Resend Email OTP."""
    if current_user.is_authenticated:
        return redirect(url_for('colorizer'))

    if 'pending_user_id' not in session or 'pending_email' not in session:
        return redirect(url_for('login', error="Session expired."))

    otp = generate_otp()
    session['pending_otp'] = otp
    send_otp_email(session['pending_email'], otp)
    flash("A new verification code has been sent to your email.", "success")
    return redirect(url_for('verify_otp'))


# ============== MFA ROUTES ==============

@app.route('/mfa/challenge', methods=['GET', 'POST'])
def mfa_challenge():
    """Second step of login for users with MFA enabled."""
    user_id = session.get('pre_mfa_user_id')
    if not user_id:
        return redirect(url_for('login'))

    user = User.get(user_id)
    if not user or not user.mfa_enabled:
        session.pop('pre_mfa_user_id', None)
        return redirect(url_for('login'))

    error = None
    if request.method == 'POST':
        code = request.form.get('code', '').strip()
        client_ip = get_client_ip()

        is_allowed, _, lockout = check_rate_limit(client_ip, max_attempts=5)
        if not is_allowed:
            return render_template('mfa_challenge.html', error=f"Too many attempts. Locked for {lockout} min.")

        is_valid = False
        is_backup = False
        if len(code) == 8:
            is_valid = verify_backup_code(user.id, code)
            is_backup = True
        else:
            is_valid = verify_totp(user.mfa_secret, code)

        if is_valid:
            remember = session.get('pre_mfa_remember', False)
            login_user(user, remember=remember)
            store_session_fingerprint()

            session.pop('pre_mfa_user_id', None)
            session.pop('pre_mfa_remember', None)
            clear_failed_attempts(client_ip)
            log_login_attempt(client_ip, user.email, True, mfa_attempt=True)

            if is_backup:
                return redirect(url_for('settings', msg='Backup code used safely.'))
            if user.role == 'admin':
                return redirect(url_for('admin_dashboard'))
            return redirect(url_for('colorizer'))
        else:
            error = 'Invalid authentication code.'
            log_login_attempt(client_ip, user.email, False, mfa_attempt=True)

    return render_template('mfa_challenge.html', error=error)


@app.route('/mfa/setup', methods=['GET', 'POST'])
@login_required
def mfa_setup():
    """Setup MFA / Generate QR."""
    if current_user.mfa_enabled:
        return redirect(url_for('settings'))

    if not QR_AVAILABLE:
        return "MFA requires qrcode and pyotp packages.", 500

    error = None
    if request.method == 'GET':
        secret = generate_mfa_secret()
        session['pending_mfa_secret'] = secret
        uri = get_totp_uri(secret, current_user.email)

        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(uri)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        
        buffered = BytesIO()
        img.save(buffered, format="PNG")
        qr_b64 = base64.b64encode(buffered.getvalue()).decode("utf-8")

        return render_template('mfa_setup.html', qr_b64=qr_b64, secret=secret)

    if request.method == 'POST':
        code = request.form.get('code', '')
        secret = session.get('pending_mfa_secret')

        if not secret:
            return redirect(url_for('mfa_setup'))

        if verify_totp(secret, code):
            backup_codes = enable_mfa(current_user.id, secret)
            session.pop('pending_mfa_secret', None)
            return render_template('mfa_success.html', backup_codes=backup_codes)
        else:
            error = "Invalid code. Please try again."
            uri = get_totp_uri(secret, current_user.email)
            qr = qrcode.QRCode(version=1, box_size=10, border=5)
            qr.add_data(uri)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")
            buffered = BytesIO()
            img.save(buffered, format="PNG")
            qr_b64 = base64.b64encode(buffered.getvalue()).decode("utf-8")
            return render_template('mfa_setup.html', qr_b64=qr_b64, secret=secret, error=error)


@app.route('/mfa/disable', methods=['POST'])
@login_required
def modify_mfa():
    """Disable MFA."""
    password = request.form.get('password', '')
    success, _ = authenticate_user(current_user.email, password)
    if not success:
        return redirect(url_for('settings', error='Incorrect password.'))

    disable_mfa(current_user.id)
    return redirect(url_for('settings', success='MFA has been disabled.'))


# ============== ACCOUNT SETTINGS ==============

@app.route('/settings', methods=['GET'])
@login_required
def settings():
    error = request.args.get('error')
    success = request.args.get('success')
    msg = request.args.get('msg')
    return render_template('settings.html', user=current_user, error=error, success=success, msg=msg)

@app.route('/settings/password', methods=['POST'])
@login_required
def update_password():
    old = request.form.get('old_password')
    new = request.form.get('new_password')
    conf = request.form.get('confirm_password')

    if new != conf:
        return redirect(url_for('settings', error="New passwords do not match."))

    success, err = change_password(current_user.id, old, new)
    if success:
        return redirect(url_for('settings', success="Password updated successfully."))
    return redirect(url_for('settings', error=err))


# ============== PUBLIC ROUTES ==============
@app.route('/')
def landing():
    if current_user.is_authenticated:
        return redirect(url_for('colorizer'))
    return render_template('landing.html')


# ============== PROTECTED APP ROUTES ==============

@app.route('/colorizer')
@permission_required('colorize')
def colorizer():
    return render_template('index.html', user=current_user)

@app.route('/upload', methods=['POST'])
@permission_required('colorize')
def upload_file():
    # Free up space before processing new upload
    cleanup_storage(max_age_seconds=300) # Keep for only 5 mins on busy servers
    
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    if not allowed_file(file.filename):
        return jsonify({'error': 'Invalid file type. Allowed: PNG, JPG, JPEG, BMP, WEBP'}), 400
    
    is_clean, vt_error = check_image_security(file)
    if not is_clean:
        if vt_error == "Upload blocked due to security reasons":
            logout_user()
            session.clear()
        return jsonify({'error': vt_error}), 403
        
    try:
        original_filename = secure_filename(file.filename)
        unique_id = str(uuid.uuid4())[:8]
        filename = f"{unique_id}_{original_filename}"
        
        input_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(input_path)
        
        file_size_kb = os.path.getsize(input_path) / 1024
        
        # Use Pillow to get dimensions without loading the whole image into RAM
        try:
            with PilImage.open(input_path) as pimg:
                width, height = pimg.size
        except Exception:
            os.remove(input_path)
            return jsonify({'error': 'Invalid image file or format'}), 400
        
        output_filename = f"colorized_{filename}"
        output_path = os.path.join(COLORIZED_FOLDER, output_filename)
        
        start_time = time.time()
        success, result = colorize_image(input_path, output_path)
        processing_time = time.time() - start_time
        
        # Immediate cleanup of memory after intensive processing
        gc.collect()
        
        if success:
            quality_score = result
            
            # Generate base64 data URL for immediate display
            output_data_url = None
            try:
                with open(output_path, 'rb') as img_file:
                    img_bytes = img_file.read()
                    ext = os.path.splitext(output_path)[1].lower()
                    mime = {'jpg': 'image/jpeg', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png', '.webp': 'image/webp', '.bmp': 'image/bmp'}.get(ext, 'image/jpeg')
                    output_data_url = f"data:{mime};base64,{base64.b64encode(img_bytes).decode('utf-8')}"
            except Exception as e:
                print(f"Base64 encoding error: {e}")
            
            # Cloudinary Upload (Removes local size limits)
            final_url = f'/static/results/{output_filename}'
            if HAS_CLOUDINARY:
                try:
                    upload_res = cloudinary.uploader.upload(output_path, 
                                                           folder="colourizer_results",
                                                           public_id=output_filename.split('.')[0])
                    final_url = upload_res.get('secure_url', final_url)
                    # Delete local copy after sync to cloud
                    if os.path.exists(output_path): os.remove(output_path)
                except Exception as e:
                    print(f"Cloudinary upload error: {e}")

            # Send result email
            send_result_email(current_user.email, output_path if not HAS_CLOUDINARY else final_url)

            log_colorization(
                original_filename=original_filename, filename=output_filename,
                image_width=width, image_height=height,
                file_size_kb=file_size_kb, processing_time_seconds=processing_time,
                quality_score=quality_score, status='success', user_id=current_user.id,
                output_url=final_url
            )

            # Manual history record and credit deduction from existing logic
            conn = get_db_connection()
            try:
                with get_db_cursor(conn) as cursor:
                    cursor.execute('''
                        INSERT INTO history (user_id, original_filename, filename, width, height, processing_time, quality_score, status)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ''', (current_user.id, original_filename, output_filename, width, height,
                          round(processing_time, 2), quality_score, 'success'))

                    cursor.execute(
                        'UPDATE users SET credits = credits - 1 WHERE id = %s AND credits > 0',
                        (current_user.id,)
                    )
                conn.commit()
            finally:
                conn.close()

            return jsonify({
                'success': True, 
                'input_url': f'/static/uploads/{filename}',
                'output_url': final_url,
                'output_data_url': output_data_url,
                'filename': output_filename, 
                'original_filename': original_filename,
                'processing_time': round(processing_time, 2), 
                'quality_score': quality_score,
                'dimensions': f"{width}x{height}", 
                'file_size_kb': round(file_size_kb, 1)
            })
        else:
            log_colorization(
                original_filename=original_filename, filename=filename,
                image_width=width, image_height=height,
                file_size_kb=file_size_kb, processing_time_seconds=processing_time,
                quality_score=0, status='failed', error_message=result, user_id=current_user.id
            )
            return jsonify({'error': result}), 500
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/download/<filename>')
@login_required
def download_file(filename):
    file_path = os.path.join(COLORIZED_FOLDER, filename)
    if os.path.exists(file_path):
        return send_file(file_path, as_attachment=True)
    return jsonify({'error': 'File not found'}), 404

@app.route('/static/results/<filename>')
def serve_colorized(filename):
    # Ensure folder exists
    if not os.path.exists(COLORIZED_FOLDER):
        os.makedirs(COLORIZED_FOLDER, exist_ok=True)
    file_path = os.path.join(COLORIZED_FOLDER, filename)
    if os.path.exists(file_path):
        return send_file(file_path)
    # Check if we should try Cloudinary fallback here? 
    # For now, just return 404 but with more info
    print(f"⚠️ STATIC FILE NOT FOUND: {file_path}")
    return jsonify({'error': 'File not found', 'path': file_path}), 404

@app.route('/dashboard')
@permission_required('view_own_history')
def dashboard():
    history = get_user_history(current_user.id)
    total_images = len(history)
    success_count = sum(1 for item in history if item['status'] == 'success')
    avg_quality = 0
    avg_processing_time = 0
    
    if success_count > 0:
        successful_items = [item for item in history if item['status'] == 'success']
        avg_quality = sum(item.get('quality_score', 0) or 0 for item in successful_items) / success_count
        avg_processing_time = sum(item.get('processing_time', 0) or 0 for item in successful_items) / len(successful_items)
    
    stats = {
        'total': total_images,
        'success_rate': round((success_count / total_images * 100) if total_images > 0 else 0, 1),
        'avg_quality': round(avg_quality, 1),
        'avg_processing_time': round(avg_processing_time, 2)
    }
    
    billing = {
        'credits': current_user.credits, 
        'plan': current_user.plan, 
        'next_billing': 'N/A', 
        'credits_percentage': min(100, int((current_user.credits / 1000) * 100)) if current_user.plan == 'FREE' else 100
    }
    
    return render_template('dashboard.html', user=current_user, history=history, stats=stats, billing=billing)

@app.route('/analytics')
@permission_required('view_own_history')
def analytics():
    try:
        return jsonify(get_analytics_summary())
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/health')
def health():
    try:
        from colorizer import _available_ram_mb
        get_colorizer()
        return jsonify({
            'status': 'healthy', 
            'model_loaded': True,
            'cloudinary_active': HAS_CLOUDINARY,
            'free_ram_mb': _available_ram_mb(),
            'storage_limit': 'Unlimited (Cloudinary)' if HAS_CLOUDINARY else 'Limited (Local)'
        })
    except Exception as e:
        return jsonify({'status': 'unhealthy', 'error': str(e)}), 503


# ============== ADMIN ROUTES ==============

@app.route('/admin')
@permission_required('view_admin_panel')
def admin_dashboard():
    roles = get_all_roles()
    return render_template('admin.html', user=current_user, roles=roles)

@app.route('/admin/api/stats')
@permission_required('view_admin_panel')
def admin_stats():
    try:
        return jsonify(get_global_stats())
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/admin/api/users')
@permission_required('view_admin_panel')
def admin_users():
    try:
        users = get_all_users()
        for u in users:
            if u.get('created_at'): u['created_at'] = safe_isoformat(u['created_at'])
            if u.get('last_activity'): u['last_activity'] = safe_isoformat(u['last_activity'])
        return jsonify(users)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/admin/api/logs')
@permission_required('view_all_logs')
def admin_logs():
    try:
        return jsonify(get_all_logs())
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/admin/api/security')
@permission_required('view_security_logs')
def admin_security():
    try:
        attempts = get_recent_login_attempts(limit=100)
        for a in attempts:
            if a.get('attempted_at'): a['attempted_at'] = safe_isoformat(a['attempted_at'])
        return jsonify(attempts)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/admin/api/audit')
@permission_required('view_admin_panel')
def admin_audit():
    try:
        from auth import get_db_connection
        conn = get_db_connection()
        try:
            
            with get_db_cursor(conn) as cur:
                cur.execute("""
                    SELECT a.id, a.admin_id, a.action, a.target_user_id,
                           a.details, a.performed_at
                    FROM admin_actions a
                    ORDER BY a.performed_at DESC
                    LIMIT 200
                """)
                rows = [dict(r) for r in cur.fetchall()]
            for r in rows:
                if r.get('performed_at'):
                    r['performed_at'] = safe_isoformat(r['performed_at'])
            return jsonify(rows)
        finally:
            conn.close()
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/admin/api/users/<int:user_id>/ban', methods=['POST'])
@permission_required('manage_users')
def admin_ban_user(user_id):
    if user_id == current_user.id:
        return jsonify({'error': 'You cannot ban yourself'}), 400
    new_state, error = toggle_user_ban(user_id)
    if error:
        return jsonify({'error': error}), 404
    action = 'ban_user' if new_state else 'unban_user'
    log_admin_action(current_user.id, action, user_id)
    return jsonify({'success': True, 'is_banned': new_state})

@app.route('/admin/api/users/<int:user_id>/role', methods=['POST'])
@permission_required('change_roles')
def admin_change_role(user_id):
    if user_id == current_user.id:
        return jsonify({'error': 'You cannot change your own role here'}), 400
    data = request.json or {}
    new_role = data.get('role', '').strip().lower()
    success, error = change_user_role(user_id, new_role)
    if not success:
        return jsonify({'error': error}), 400
    log_admin_action(current_user.id, f'change_role_{new_role}', user_id)
    return jsonify({'success': True, 'role': new_role})

@app.route('/admin/api/users/<int:user_id>/delete', methods=['POST'])
@permission_required('delete_users')
def admin_delete_user(user_id):
    if user_id == current_user.id:
        return jsonify({'error': 'You cannot delete yourself'}), 400
    success, error = delete_user_by_id(user_id)
    if not success:
        return jsonify({'error': error}), 500
    log_admin_action(current_user.id, 'delete_user', user_id)
    return jsonify({'success': True})


if __name__ == '__main__':
    print("\n" + "="*60)
    print("🎨 Image Colorization — SECURE EDITION")
    print("="*60)
    print(f"✅ RBAC Engine: Active")
    print(f"✅ TOTP MFA Module: {'Active' if PYOTP_AVAILABLE and QR_AVAILABLE else 'Disabled'}")
    print(f"✅ CSRF Protection: Active")
    print(f"✅ Session Security: Active")
    print("\n📍 Server starting at: http://localhost:5000")
    print("="*60 + "\n")
    
    app.run(debug=False, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
