"""
auth/routes.py — Authentication Blueprint
Includes both user and admin authentication
"""

from flask import Blueprint, render_template, redirect, url_for, flash, request, session, current_app
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash, generate_password_hash
from functools import wraps
from datetime import datetime, timedelta

import secrets
import string
from datetime import datetime, timedelta
from flask import jsonify, request, session
from flask_mail import Message
import pyotp
from app.extensions import db, mail, login_manager, migrate

from app.models import User, Shipment, ShipmentEvent, Package, Subscription, PLANS, \
    NotificationPreference, CURRENCIES, PaymentRequest, PaymentMethod, SupportTicket, Notification

auth_bp = Blueprint('auth', __name__)

# ────────────────────────────────────────────
# User Authentication (Existing)
# ────────────────────────────────────────────

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """User login with email and password."""
    # If already authenticated, redirect appropriately
    if current_user.is_authenticated:
        if current_user.is_admin:
            return redirect(url_for('admin.dashboard'))
        return redirect(url_for('user.dashboard'))
    
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        remember = request.form.get('remember') == 'on'
        
        user = User.query.filter_by(email=email).first()
        
        if user and check_password_hash(user.password_hash, password):
            if not user.is_active:
                flash('Your account has been deactivated. Please contact support.', 'error')
                return redirect(url_for('auth.login'))
            
            # Check if user is admin - reject if trying to use regular login
            if user.is_admin:
                flash('Admin accounts must use the admin login page.', 'warning')
                return redirect(url_for('auth.login'))
            
            login_user(user, remember=remember)
            
            # Redirect to requested page or dashboard
            next_page = request.args.get('next')
            if next_page:
                return redirect(next_page)
            return redirect(url_for('user.dashboard'))
        else:
            flash('Invalid email or password.', 'error')
    
    return render_template('auth/login.html')

    
# @auth_bp.route('/register', methods=['GET', 'POST'])
# def register():
#     """User registration."""
#     if current_user.is_authenticated:
#         return redirect(url_for('user.dashboard'))
    
#     if request.method == 'POST':
#         email = request.form.get('email', '').strip().lower()
#         full_name = request.form.get('full_name', '').strip()
#         password = request.form.get('password', '')
#         confirm_password = request.form.get('confirm_password', '')
        
#         # Validation
#         if not all([email, full_name, password]):
#             flash('Please fill in all fields.', 'error')
#             return redirect(url_for('auth.register'))
        
#         if password != confirm_password:
#             flash('Passwords do not match.', 'error')
#             return redirect(url_for('auth.register'))
        
#         if len(password) < 8:
#             flash('Password must be at least 8 characters.', 'error')
#             return redirect(url_for('auth.register'))
        
#         if User.query.filter_by(email=email).first():
#             flash('Email already registered.', 'error')
#             return redirect(url_for('auth.register'))
        
#         # Create user
#         user = User(
#             email=email,
#             full_name=full_name,
#             password_hash=generate_password_hash(password),
#             is_admin=False
#         )
#         db.session.add(user)
#         db.session.flush()
        
#         # Create free subscription
#         from models import Subscription
#         sub = Subscription(user_id=user.id, plan_id='free')
#         db.session.add(sub)
        
#         # Create notification preferences
#         from models import NotificationPreference
#         prefs = NotificationPreference(user_id=user.id)
#         db.session.add(prefs)
        
#         db.session.commit()
        
#         flash('Account created successfully! Please log in.', 'success')
#         return redirect(url_for('auth.login'))
    
#     return render_template('auth/register.html')


@auth_bp.route('/logout')
@login_required
def logout():
    """Logout user or admin."""
    # Clear impersonation data if present
    session.pop('impersonator_id', None)
    session.pop('impersonator_name', None)
    
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('auth.login'))


@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    """Password reset request."""
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        user = User.query.filter_by(email=email).first()
        
        if user:
            # Generate reset token
            from secrets import token_urlsafe
            token = token_urlsafe(32)
            user.reset_token = token
            user.reset_token_expires = datetime.utcnow() + timedelta(hours=24)
            db.session.commit()
            
            # Send email (implement with your email service)
            # send_reset_email(user.email, token)
            
            current_app.logger.info(f'Password reset requested for {email}')
        
        # Always show success to prevent email enumeration
        flash('If an account exists with that email, you will receive reset instructions.', 'info')
        return redirect(url_for('auth.login'))
    
    return render_template('auth/forgot_password.html')


# ────────────────────────────────────────────
# Admin Authentication
# ────────────────────────────────────────────

@auth_bp.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    """Admin-only login portal."""
    # If already logged in as admin, redirect to admin dashboard
    if current_user.is_authenticated:
        if current_user.is_admin:
            return redirect(url_for('admin.dashboard'))
        else:
            # Regular user trying to access admin - logout first
            logout_user()
            flash('Please log in with admin credentials.', 'warning')
    
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        remember = request.form.get('remember') == 'on'
        
        # Rate limiting check (simple implementation)
        login_attempts = session.get('admin_login_attempts', 0)
        last_attempt = session.get('admin_login_last_attempt')
        
        if login_attempts >= 5:
            if last_attempt and (datetime.utcnow() - datetime.fromisoformat(last_attempt)).seconds < 300:
                flash('Too many failed attempts. Please try again in 5 minutes.', 'error')
                current_app.logger.warning(f'Admin login rate limited for {email}')
                return redirect(url_for('auth.admin_login'))
            else:
                # Reset after 5 minutes
                session.pop('admin_login_attempts', None)
        
        user = User.query.filter_by(email=email).first()
        
        # Check if user exists, password matches, AND is admin
        if user and check_password_hash(user.password_hash, password):
            if not user.is_admin:
                flash('Access denied. Admin privileges required.', 'error')
                current_app.logger.warning(f'Non-admin {email} attempted admin login')
                
                # Increment failed attempts
                session['admin_login_attempts'] = login_attempts + 1
                session['admin_login_last_attempt'] = datetime.utcnow().isoformat()
                
                return redirect(url_for('auth.admin_login'))
            
            if not getattr(user, 'is_active', True):
                flash('Your admin account has been deactivated.', 'error')
                return redirect(url_for('auth.admin_login'))
            
            # Successful admin login
            session.pop('admin_login_attempts', None)
            login_user(user, remember=remember)
            
            # Log admin access
            current_app.logger.info(f'Admin login successful: {email} from {request.remote_addr}')
            
            # Update last login (add field to model if needed)
            user.last_login_at = datetime.utcnow()
            db.session.commit()
            
            next_page = request.args.get('next')
            if next_page:
                return redirect(next_page)
            return redirect(url_for('admin.dashboard'))
        else:
            flash('Invalid admin credentials.', 'error')
            
            # Increment failed attempts
            session['admin_login_attempts'] = login_attempts + 1
            session['admin_login_last_attempt'] = datetime.utcnow().isoformat()
            
            current_app.logger.warning(f'Failed admin login attempt for {email} from {request.remote_addr}')
    
    return render_template('auth/admin_login.html')


import os
from functools import wraps

def require_admin_key(f):
    """Decorator to verify admin registration key."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        admin_key = request.form.get('admin_key') or request.json.get('admin_key')
        expected_key = os.environ.get('ADMIN_REGISTRATION_KEY', 'your-secure-admin-key-here')
        
        if not admin_key or admin_key != expected_key:
            if request.is_json:
                return jsonify({'success': False, 'error': 'Invalid admin access key'}), 403
            flash('Invalid or missing admin access key', 'error')
            return redirect(url_for('auth.admin_register'))
        
        return f(*args, **kwargs)
    return decorated_function

@auth_bp.route('/admin/register/', methods=['GET', 'POST'])
def admin_register():
    """Admin registration - 2 step process."""
    if current_user.is_authenticated:
        return redirect(url_for('admin.dashboard'))
    
    if request.method == 'POST':
        # All data comes in single POST from step 2
        admin_key = request.form.get('admin_key', '').strip()
        expected_key = os.environ.get('ADMIN_REGISTRATION_KEY')
        
        if not expected_key or admin_key != expected_key:
            current_app.logger.warning(f'Invalid admin key from IP: {request.remote_addr}')
            flash('Invalid access key', 'error')
            return redirect(url_for('auth.admin_register'))
        
        email = request.form.get('email', '').strip().lower()
        full_name = request.form.get('full_name', '').strip()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        admin_level = request.form.get('admin_level', '')
        
        if password != confirm_password:
            flash('Passwords do not match', 'error')
            return redirect(url_for('auth.admin_register'))
        
        # Strict validation
        if len(password) < 12 or not (any(c.isupper() for c in password) and 
                any(c.isdigit() for c in password) and 
                any(c in '!@#$%^&*(),.?":{}|<>' for c in password)):
            flash('Password does not meet security requirements', 'error')
            return redirect(url_for('auth.admin_register'))
        
        if User.query.filter_by(email=email).first():
            flash('Email exists', 'error')
            return redirect(url_for('auth.admin_register'))
        
        try:
            user = User(
                email=email,
                full_name=full_name,
                password_hash=generate_password_hash(password, method='pbkdf2:sha256:600000'),
                is_admin=True,
                is_active=True,
                company='Uthao Logistics',
                currency='USD'
            )
            db.session.add(user)
            db.session.flush()
            
            db.session.add(Subscription(user_id=user.id, plan_id='enterprise'))
            db.session.add(NotificationPreference(user_id=user.id))
            db.session.commit()
            
            current_app.logger.info(f'Admin created: {email} ({admin_level})')
            login_user(user)
            flash('Admin created', 'success')
            return redirect(url_for('admin.dashboard'))
            
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f'Admin reg fail: {e}')
            flash('Creation failed', 'error')
            return redirect(url_for('auth.admin_register'))
    
    return render_template('auth/admin_register.html')



@auth_bp.route('/admin/setup-key', methods=['POST'])
@require_admin_key
def generate_admin_key():
    """Generate a temporary admin registration key (for superusers only)."""
    import secrets
    temp_key = f"UTHAO-ADMIN-{secrets.token_urlsafe(16)}"
    
    # In production, you might want to store this in Redis with expiration
    return jsonify({
        'success': True,
        'key': temp_key,
        'expires_in': '24 hours',
        'note': 'Share this key securely with authorized personnel only'
    })
# ────────────────────────────────────────────
# Security Middleware
# ────────────────────────────────────────────

@auth_bp.before_app_request
def check_admin_session():
    """Additional security checks for admin routes."""
    if request.path.startswith('/admin/'):
        # Skip login routes
        if request.endpoint in ['auth.admin_login', 'auth.admin_setup', 'static']:
            return
        
        # Ensure user is authenticated and admin
        if not current_user.is_authenticated:
            return redirect(url_for('auth.admin_login', next=request.url))
        
        if not current_user.is_admin:
            flash('Admin access required.', 'error')
            return redirect(url_for('user.dashboard'))
        
        # Check for impersonation and prevent access to admin while impersonating
        if session.get('impersonator_id'):
            flash('Cannot access admin panel while impersonating a user.', 'error')
            return redirect(url_for('user.dashboard'))


# Add these to your auth_bp routes

def get_mail():
    """Helper to get mail instance from app extensions."""
    return current_app.extensions.get('mail')

@auth_bp.route('/check-email', methods=['POST'])
def check_email():
    """Check if email is already registered."""
    data = request.get_json()
    email = data.get('email', '').strip().lower()
    
    exists = User.query.filter_by(email=email).first() is not None
    return jsonify({'exists': exists})

@auth_bp.route('/send-otp', methods=['POST'])
def send_otp():
    """Send OTP to email for verification."""
    data = request.get_json()
    email = data.get('email', '').strip().lower()
    
    # Generate 6-digit OTP
    otp = ''.join(secrets.choice(string.digits) for _ in range(6))
    
    # Store in session with expiration (10 minutes)
    session['otp_data'] = {
        'email': email,
        'otp': otp,
        'expires': (datetime.utcnow() + timedelta(minutes=10)).isoformat(),
        'attempts': 0
    }
    
    # Send email
    try:
        mail = get_mail()  # or just use 'mail' if imported directly
        msg = Message(
            subject='Your Uthao Verification Code',
            recipients=[email],
            html=f'''
            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; background: #f4f4f4;">
                <div style="background: white; padding: 30px; border-radius: 10px; text-align: center; border-top: 4px solid #f27f0d;">
                    <h2 style="color: #221910; margin-bottom: 20px;">Verify Your Email</h2>
                    <p style="color: #666; margin-bottom: 30px;">Use this code to complete your registration:</p>
                    <div style="background: #fff8f0; padding: 20px; border-radius: 8px; margin: 20px 0; border: 2px dashed #f27f0d;">
                        <span style="font-size: 36px; font-weight: bold; color: #f27f0d; letter-spacing: 8px;">{otp}</span>
                    </div>
                    <p style="color: #999; font-size: 12px; margin-top: 20px;">This code expires in 10 minutes.</p>
                    <p style="color: #999; font-size: 12px;">If you didn't request this, please ignore this email.</p>
                </div>
            </div>
            '''
        )
        mail.send(msg)
        return jsonify({'success': True})
    except Exception as e:
        current_app.logger.error(f"Failed to send OTP: {e}")
        return jsonify({'success': False, 'error': 'Failed to send email'}), 500

    
@auth_bp.route('/verify-otp', methods=['POST'])
def verify_otp():
    """Verify OTP code."""
    data = request.get_json()
    email = data.get('email', '').strip().lower()
    otp = data.get('otp', '')
    
    otp_data = session.get('otp_data')
    
    if not otp_data:
        return jsonify({'success': False, 'error': 'No OTP requested'}), 400
    
    # Check expiration
    expires = datetime.fromisoformat(otp_data['expires'])
    if datetime.utcnow() > expires:
        session.pop('otp_data', None)
        return jsonify({'success': False, 'error': 'OTP expired'}), 400
    
    # Check attempts
    if otp_data.get('attempts', 0) >= 3:
        session.pop('otp_data', None)
        return jsonify({'success': False, 'error': 'Too many attempts'}), 400
    
    # Verify
    if otp_data['email'] != email or otp_data['otp'] != otp:
        otp_data['attempts'] = otp_data.get('attempts', 0) + 1
        session['otp_data'] = otp_data
        return jsonify({'success': False, 'error': 'Invalid OTP'}), 400
    
    # Mark as verified
    session['email_verified'] = email
    session.pop('otp_data', None)
    
    return jsonify({'success': True})

@auth_bp.route('/send-magic-link', methods=['POST'])
def send_magic_link():
    """Send magic link for email verification."""
    data = request.get_json()
    email = data.get('email', '').strip().lower()
    link_type = data.get('type', 'registration')
    
    # Generate token
    token = secrets.token_urlsafe(32)
    
    # Store token
    session['magic_link'] = {
        'email': email,
        'token': token,
        'type': link_type,
        'expires': (datetime.utcnow() + timedelta(hours=24)).isoformat()
    }
    
    # Build link
    verify_url = url_for('auth.verify_magic_link', token=token, _external=True)
    
    try:
        msg = Message(
            'Verify Your Email - Magic Link',
            recipients=[email],
            html=f'''
            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; background: #f4f4f4;">
                <div style="background: white; padding: 30px; border-radius: 10px; text-align: center;">
                    <h2 style="color: #333; margin-bottom: 20px;">Verify Your Email</h2>
                    <p style="color: #666; margin-bottom: 30px;">Click the button below to verify your email address:</p>
                    <a href="{verify_url}" style="display: inline-block; background: #8b5cf6; color: white; padding: 15px 30px; text-decoration: none; border-radius: 8px; font-weight: bold; margin: 20px 0;">Verify Email</a>
                    <p style="color: #999; font-size: 12px; margin-top: 20px;">Or copy this link: {verify_url}</p>
                    <p style="color: #999; font-size: 12px;">This link expires in 24 hours.</p>
                </div>
            </div>
            '''
        )
        mail.send(msg)
        return jsonify({'success': True})
    except Exception as e:
        current_app.logger.error(f"Failed to send magic link: {e}")
        return jsonify({'success': False}), 500

@auth_bp.route('/verify-magic-link/<token>')
def verify_magic_link(token):
    """Handle magic link verification."""
    magic_data = session.get('magic_link')
    
    if not magic_data or magic_data['token'] != token:
        flash('Invalid or expired link', 'error')
        return redirect(url_for('auth.register'))
    
    # Check expiration
    expires = datetime.fromisoformat(magic_data['expires'])
    if datetime.utcnow() > expires:
        flash('Link has expired', 'error')
        return redirect(url_for('auth.register'))
    
    # Mark as verified
    session['email_verified'] = magic_data['email']
    session.pop('magic_link', None)
    
    # If coming from registration flow, redirect to step 3
    if magic_data.get('type') == 'registration':
        # Store temp data if coming back
        return redirect(url_for('auth.register_step3'))
    
    flash('Email verified successfully!', 'success')
    return redirect(url_for('auth.login'))

@auth_bp.route('/register-complete/', methods=['POST'])
def register_complete():
    """Complete registration after verification."""
    data = request.get_json()
    
    # Verify email was verified
    verified_email = session.get('email_verified')
    if not verified_email or verified_email != data.get('email'):
        return jsonify({'success': False, 'message': 'Email not verified'}), 400
    
    try:
        # Create user
        user = User(
            email=data['email'],
            full_name=data['full_name'],
            password_hash=generate_password_hash(data['password']),
            company=data.get('company', ''),
            phone=data.get('phone', ''),
            currency=data.get('currency', 'USD'),
            is_admin=False
        )
        db.session.add(user)
        db.session.flush()
        
        # Create subscription
        sub = Subscription(user_id=user.id, plan_id='free')
        db.session.add(sub)
        
        # Create notification preferences
        prefs = NotificationPreference(user_id=user.id)
        db.session.add(prefs)
        
        db.session.commit()
        
        # Log user in
        login_user(user)
        
        # Clear session data
        session.pop('email_verified', None)
        session.pop('registration_data', None)
        
        return jsonify({
            'success': True,
            'redirect': url_for('user.dashboard')
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Registration failed: {e}")
        return jsonify({'success': False, 'message': 'Registration failed'}), 500

# Update existing register route to just redirect if already in flow
@auth_bp.route('/register/', methods=['GET'])
def register():
    """Registration page."""
    if current_user.is_authenticated:
        return redirect(url_for('user.dashboard'))
    return render_template('auth/register.html')

@auth_bp.route('/register/step3', methods=['GET'])
def register_step3():
    """Step 3 of registration (after verification)."""
    if current_user.is_authenticated:
        return redirect(url_for('user.dashboard'))
    
    if 'email_verified' not in session:
        return redirect(url_for('auth.register'))
    
    return render_template('auth/register.html', step=3)