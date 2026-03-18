"""
user/routes.py — UTHAO User Blueprint
Includes JSON API endpoints consumed by the frontend JS.
"""

import os
import secrets
from flask import Blueprint, render_template, session, redirect, url_for, \
    flash, request, jsonify, abort, current_app, Response, stream_with_context, json
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from werkzeug.security import check_password_hash, generate_password_hash
from models import Shipment, ShipmentEvent, Package, Subscription, PLANS, \
    NotificationPreference, CURRENCIES, PaymentRequest, PaymentMethod, SupportTicket, Notification, PackageImage, ShipmentPayment
from extensions import db, mail, login_manager, migrate

from datetime import datetime, timedelta
import random
import string
from sqlalchemy.orm import joinedload
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
import cloudinary
import cloudinary.api
import requests
from io import BytesIO



user_bp = Blueprint('user', __name__)

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'pdf'}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB for payment proofs

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# ────────────────────────────────────────────
# FIXED: Improved file upload helper
# ────────────────────────────────────────────

# def save_uploaded_file(file, folder, prefix):
#     """Save uploaded file and return URL path. FIXED version with proper validation."""
#     if not file:
#         raise ValueError('No file provided')
    
#     if not file.filename or not file.filename.strip():
#         raise ValueError('No file selected')
    
#     # Check extension before reading stream
#     if not allowed_file(file.filename):
#         raise ValueError('Invalid file type. Allowed: PNG, JPG, JPEG, GIF, WEBP, PDF')
    
#     # Read content for size validation (this consumes the stream)
#     file_content = file.read()
    
#     if not file_content:
#         raise ValueError('Empty file')
    
#     size = len(file_content)
#     if size > MAX_FILE_SIZE:
#         raise ValueError(f'File too large. Maximum size: {MAX_FILE_SIZE / (1024*1024):.1f}MB')
    
#     # Generate secure filename
#     ext = secure_filename(file.filename).rsplit('.', 1)[1].lower()
#     filename = f"{prefix}_{current_user.id}_{secrets.token_hex(8)}.{ext}"
    
#     upload_folder = current_app.config.get(
#         'UPLOAD_FOLDER', 
#         os.path.join(current_app.root_path, 'static', 'uploads')
#     )
#     upload_path = os.path.join(upload_folder, folder)
#     os.makedirs(upload_path, exist_ok=True)
    
#     filepath = os.path.join(upload_path, filename)
    
#     # Write the content we already read
#     with open(filepath, 'wb') as f:
#         f.write(file_content)
    
#     return f"/uploads/{folder}/{filename}"


def save_uploaded_file(file, folder, prefix):
    if not file or not file.filename or not file.filename.strip():
        raise ValueError('No file selected')
    if not allowed_file(file.filename):
        raise ValueError('Invalid file type. Allowed: PNG, JPG, JPEG, GIF, WEBP, PDF')

    file_content = file.read()
    if not file_content:
        raise ValueError('Empty file')
    if len(file_content) > MAX_FILE_SIZE:
        raise ValueError(f'File too large. Maximum size: {MAX_FILE_SIZE / (1024*1024):.1f}MB')

    if os.environ.get('CLOUDINARY_CLOUD_NAME'):
        import cloudinary
        import cloudinary.uploader
        import io

        cloudinary.config(
            cloud_name=os.environ['CLOUDINARY_CLOUD_NAME'],
            api_key=os.environ['CLOUDINARY_API_KEY'],
            api_secret=os.environ['CLOUDINARY_API_SECRET']
        )
        public_id = f"uthao/{folder}/{prefix}_{current_user.id}_{secrets.token_hex(8)}"
        result = cloudinary.uploader.upload(
            io.BytesIO(file_content),
            public_id=public_id,
            resource_type='auto'
        )
        return result['secure_url']

    # Local fallback (development)
    ext = secure_filename(file.filename).rsplit('.', 1)[1].lower()
    filename = f"{prefix}_{current_user.id}_{secrets.token_hex(8)}.{ext}"
    upload_folder = current_app.config.get(
        'UPLOAD_FOLDER',
        os.path.join(current_app.root_path, 'static', 'uploads')
    )
    upload_path = os.path.join(upload_folder, folder)
    os.makedirs(upload_path, exist_ok=True)
    with open(os.path.join(upload_path, filename), 'wb') as f:
        f.write(file_content)
    return f"/uploads/{folder}/{filename}"


def shipment_to_dict(s, include_events=False):
    """Serialize a Shipment model to a JSON-safe dict."""
    data = {
        'id':               s.id,
        'tracking_number':  s.tracking_number,
        'origin':           s.origin or '',
        'destination':      s.destination or '',
        'origin_city':      (s.origin or '').split(',')[0].strip(),
        'destination_city': (s.destination or '').split(',')[0].strip(),
        'sender_name':      s.sender_name or '',
        'sender_phone':     s.sender_phone or '',
        'commodity':        s.commodity or 'General Cargo',
        'cargo_type':       s.commodity or 'General Cargo',
        'weight':           float(s.weight) if s.weight else 0,
        'dimensions':       s.dimensions or '',
        'service_level':    s.service_level or 'Standard',
        'cost':             float(s.cost) if s.cost else 0,
        'status':           s.status or 'Booking Created',
        'estimated_delivery': s.estimated_delivery.isoformat() if s.estimated_delivery else None,
        'delivery_time':    '02:30 PM',
        'created_at':       s.created_at.isoformat() if s.created_at else None,
        'recipient': {
            'name':    s.receiver_name or '',
            'company': s.receiver_company or '',
            'phone':   s.receiver_phone or '',
        },
        'packages': [
            {
                'id':          p.id,
                'length':      p.length,
                'width':       p.width,
                'height':      p.height,
                'weight':      p.weight,
                'description': p.description or '',
                'stackable':   p.stackable,
                'fragile':     p.fragile,
                'dimensions':  p.dimensions_str,
            }
            for p in s.packages
        ],
    }
    if include_events:
        data['events'] = [event_to_dict(e) for e in s.events]
    return data

def event_to_dict(e):
    return {
        'id':           e.id,
        'status':       e.status or '',
        'status_label': e.status or '',
        'location':     e.location or '',
        'description':  e.description or '',
        'timestamp':    e.timestamp.isoformat() if e.timestamp else None,
    }

def generate_tracking():
    return 'UTH-' + ''.join(random.choices(string.digits, k=7))

# ────────────────────────────────────────────
# Page Routes
# ────────────────────────────────────────────

@user_bp.route('/dashboard')
@login_required
def dashboard():
    return render_template('user/dashboard.html')

@user_bp.route('/tracking')
@login_required
def tracking():
    return render_template('user/tracking.html')

@user_bp.route('/api/shipments/<tracking_number>')
@login_required
def shipment_detail(tracking_number):
    s = Shipment.query.filter_by(
        tracking_number=tracking_number,
        user_id=current_user.id
    ).first_or_404()

    return jsonify({
        "tracking_number": s.tracking_number,
        "origin": s.origin,
        "destination": s.destination,
        "status": s.status,
        "estimated_delivery": s.estimated_delivery,
        "commodity": s.commodity,
        "recipient": {
            "name": s.receiver_name,
            "company": s.receiver_company,
            "phone": s.receiver_phone
        },
        "events": [
            {
                "status": e.status,
                "description": e.description,
                "location": e.location,
                "timestamp": e.timestamp
            } for e in s.events
        ]
    })

@user_bp.route('/orders')
@login_required
def order_history():
    shipments = (
        Shipment.query
        .filter_by(user_id=current_user.id)
        .order_by(Shipment.created_at.desc())
        .all()
    )
    return render_template('user/order_history.html', shipments=shipments)

# ────────────────────────────────────────────
# Support/Help Routes
# ────────────────────────────────────────────

@user_bp.route('/support')
@login_required
def support():
    """Help center with FAQs and support options."""
    # Get user's recent tickets
    recent_tickets = SupportTicket.query.filter_by(
        user_id=current_user.id
    ).order_by(SupportTicket.created_at.desc()).limit(5).all()
    
    # FAQ categories with questions
    faq_categories = {
        'Getting Started': [
            {
                'q': 'How do I create my first shipment?',
                'a': 'Navigate to "Create Shipment" in the sidebar, fill in origin/destination details, add package information, select your preferred service level, and confirm your booking. You\'ll receive a tracking number immediately.'
            },
            {
                'q': 'What information do I need to book a shipment?',
                'a': 'You\'ll need sender and receiver details (name, phone, address), package dimensions and weight, and your preferred delivery service level (Economy, Standard, or Express).'
            },
            {
                'q': 'How do I track my shipment?',
                'a': 'Use the "Tracking" page in your sidebar or click on any tracking number in your Order History. You\'ll see real-time status updates and estimated delivery times.'
            }
        ],
        'Pricing & Billing': [
            {
                'q': 'How is shipping cost calculated?',
                'a': 'Costs are based on package weight, dimensions, origin-destination distance, and selected service level. You can see exact pricing before confirming any shipment.'
            },
            {
                'q': 'What payment methods do you accept?',
                'a': 'We accept USDT (Tether), Bitcoin, PayPal, and GBP bank transfers. All payments are processed securely through our verified payment providers.'
            },
            {
                'q': 'How do I upgrade or downgrade my plan?',
                'a': 'Go to Settings > Billing to view available plans. Upgrades require payment confirmation, while downgrades to free plans are processed immediately.'
            }
        ],
        'Shipments & Delivery': [
            {
                'q': 'What are the delivery timeframes?',
                'a': 'Economy: 7-10 business days, Standard: 3-5 business days, Express: 1-2 business days. Timeframes may vary based on destination and customs clearance.'
            },
            {
                'q': 'What happens if my shipment is delayed?',
                'a': 'We proactively monitor all shipments. If delays occur, you\'ll receive notifications with updated ETAs. For significant delays, our support team will contact you directly.'
            },
            {
                'q': 'Can I modify a shipment after booking?',
                'a': 'Modifications are possible only before pickup. Contact support immediately if you need changes. Some modifications may incur additional fees.'
            }
        ],
        'Account & Security': [
            {
                'q': 'How do I reset my password?',
                'a': 'Go to Settings > Security and click "Change Password". You\'ll need your current password to set a new one. Use a strong, unique password for security.'
            },
            {
                'q': 'Is my data secure with UTHAO?',
                'a': 'Yes, we use bank-level encryption (256-bit SSL) for all data transfers. Your payment information is never stored on our servers.'
            },
            {
                'q': 'How do I enable two-factor authentication?',
                'a': 'Navigate to Settings > Security and toggle "Enable 2FA". Follow the setup instructions to secure your account with an authenticator app.'
            }
        ]
    }
    
    return render_template(
        'user/support.html',
        faq_categories=faq_categories,
        recent_tickets=recent_tickets,
        active_plan=current_user.active_plan
    )


@user_bp.route('/help/ticket', methods=['POST'])
@login_required
def create_ticket():
    """Create a new support ticket."""
    subject = request.form.get('subject', '').strip()
    category = request.form.get('category', '').strip()
    priority = request.form.get('priority', 'medium').strip()
    message = request.form.get('message', '').strip()
    shipment_id = request.form.get('shipment_id', '').strip()
    
    # Validation
    if not subject or not message:
        flash('Please fill in all required fields.', 'error')
        return redirect(url_for('user.support'))
    
    if len(message) < 20:
        flash('Please provide more details (minimum 20 characters).', 'error')
        return redirect(url_for('user.support'))
    
    # Create ticket
    ticket = SupportTicket(
        user_id=current_user.id,
        subject=subject,
        category=category,
        priority=priority,
        message=message,
        shipment_reference=shipment_id if shipment_id else None,
        status='open'
    )
    
    db.session.add(ticket)
    db.session.commit()
    
    # Send notification email (optional)
    flash('Your support ticket has been created. We\'ll respond within 24 hours.', 'success')
    return redirect(url_for('user.support'))


@user_bp.route('/help/ticket/<int:ticket_id>')
@login_required
def view_ticket(ticket_id):
    """View specific ticket details."""
    ticket = SupportTicket.query.filter_by(
        id=ticket_id,
        user_id=current_user.id
    ).first_or_404()
    
    return render_template('user/ticket_detail.html', ticket=ticket)


@user_bp.route('/help/ticket/<int:ticket_id>/reply', methods=['POST'])
@login_required
def reply_ticket(ticket_id):
    """Add reply to existing ticket."""
    ticket = SupportTicket.query.filter_by(
        id=ticket_id,
        user_id=current_user.id
    ).first_or_404()
    
    message = request.form.get('message', '').strip()
    if not message:
        flash('Please enter a message.', 'error')
        return redirect(url_for('user.view_ticket', ticket_id=ticket_id))
    
    reply = TicketReply(
        ticket_id=ticket.id,
        user_id=current_user.id,
        message=message,
        is_staff=False
    )
    
    db.session.add(reply)
    
    # Update ticket status
    if ticket.status == 'resolved':
        ticket.status = 'open'
    
    ticket.updated_at = datetime.utcnow()
    db.session.commit()
    
    flash('Reply added successfully.', 'success')
    return redirect(url_for('user.view_ticket', ticket_id=ticket_id))


@user_bp.route('/help/search')
@login_required
def search_help():
    """Search FAQs and help articles."""
    query = request.args.get('q', '').strip().lower()
    
    if not query:
        return redirect(url_for('user.support'))
    
    # Simple search through FAQ content
    results = []
    faq_data = {
        'Getting Started': ['create shipment', 'booking', 'tracking', 'first time'],
        'Pricing & Billing': ['cost', 'price', 'payment', 'upgrade', 'plan', 'billing'],
        'Shipments & Delivery': ['delivery', 'delay', 'timeframe', 'modify', 'package'],
        'Account & Security': ['password', 'security', '2fa', 'login', 'account']
    }
    
    for category, keywords in faq_data.items():
        if any(keyword in query for keyword in keywords):
            results.append(category)
    
    return jsonify({
        'query': query,
        'suggested_categories': results,
        'message': 'Please see the relevant section in the Help Center.'
    })

@user_bp.route('/fleet')
@login_required
def fleet():
    flash('Fleet management is coming soon.', 'info')
    return redirect(url_for('user.dashboard'))

@user_bp.route('/analytics')
@login_required
def analytics():
    """Analytics dashboard for shipments and account activity."""
    from datetime import datetime, timedelta
    from sqlalchemy import func, extract
    
    # Date ranges
    today = datetime.utcnow()
    thirty_days_ago = today - timedelta(days=30)
    seven_days_ago = today - timedelta(days=7)
    
    # Get shipment statistics
    total_shipments = Shipment.query.filter_by(user_id=current_user.id).count()
    
    shipments_this_month = Shipment.query.filter(
        Shipment.user_id == current_user.id,
        Shipment.created_at >= thirty_days_ago
    ).count()
    
    shipments_this_week = Shipment.query.filter(
        Shipment.user_id == current_user.id,
        Shipment.created_at >= seven_days_ago
    ).count()
    
    # Status breakdown
    status_counts = db.session.query(
        Shipment.status,
        func.count(Shipment.id)
    ).filter_by(user_id=current_user.id).group_by(Shipment.status).all()
    
    status_data = {status: count for status, count in status_counts}
    
    # Monthly shipment trend (last 6 months)
    monthly_data = []
    monthly_labels = []
    for i in range(5, -1, -1):
        month_date = today - timedelta(days=i*30)
        month_start = month_date.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        month_end = (month_start + timedelta(days=32)).replace(day=1) - timedelta(seconds=1)
        
        count = Shipment.query.filter(
            Shipment.user_id == current_user.id,
            Shipment.created_at >= month_start,
            Shipment.created_at <= month_end
        ).count()
        
        monthly_labels.append(month_date.strftime('%b %Y'))
        monthly_data.append(count)
    
    # Spending analysis (based on shipment costs)
    total_spent = db.session.query(func.sum(Shipment.cost)).filter_by(user_id=current_user.id).scalar() or 0
    
    avg_cost = db.session.query(func.avg(Shipment.cost)).filter_by(user_id=current_user.id).scalar() or 0
    
    # Service level distribution
    service_data = db.session.query(
        Shipment.service_level,
        func.count(Shipment.id)
    ).filter_by(user_id=current_user.id).group_by(Shipment.service_level).all()
    
    # Top destinations
    top_destinations = db.session.query(
        Shipment.destination,
        func.count(Shipment.id).label('count')
    ).filter_by(user_id=current_user.id).group_by(Shipment.destination).order_by(func.count(Shipment.id).desc()).limit(5).all()
    
    # Weight statistics
    total_weight = db.session.query(func.sum(Shipment.weight)).filter_by(user_id=current_user.id).scalar() or 0
    
    # Recent activity (last 10 shipments with events)
    recent_shipments = Shipment.query.filter_by(user_id=current_user.id).order_by(Shipment.created_at.desc()).limit(10).all()
    
    # Calculate trend percentages (mock comparison to previous period)
    prev_month_shipments = Shipment.query.filter(
        Shipment.user_id == current_user.id,
        Shipment.created_at >= thirty_days_ago - timedelta(days=30),
        Shipment.created_at < thirty_days_ago
    ).count()
    
    shipment_trend = ((shipments_this_month - prev_month_shipments) / max(prev_month_shipments, 1)) * 100 if prev_month_shipments else 0
    
    # Prepare chart data
    chart_data = {
        'monthly_labels': monthly_labels,
        'monthly_data': monthly_data,
        'status_labels': list(status_data.keys()),
        'status_data': list(status_data.values()),
        'service_labels': [s[0] or 'Standard' for s in service_data],
        'service_data': [s[1] for s in service_data],
        'destination_labels': [d[0].split(',')[0] if ',' in d[0] else d[0][:20] for d in top_destinations],
        'destination_data': [d[1] for d in top_destinations]
    }
    
    return render_template(
        'user/analytics.html',
        total_shipments=total_shipments,
        shipments_this_month=shipments_this_month,
        shipments_this_week=shipments_this_week,
        total_spent=total_spent,
        avg_cost=avg_cost,
        total_weight=total_weight,
        status_data=status_data,
        recent_shipments=recent_shipments,
        shipment_trend=shipment_trend,
        chart_data=chart_data,
        active_plan=current_user.active_plan
    )

@user_bp.route('/drivers')
@login_required
def drivers():
    flash('Driver management is coming soon.', 'info')
    return redirect(url_for('user.dashboard'))

# ────────────────────────────────────────────
# Settings Routes
# ────────────────────────────────────────────

def _handle_profile_update(request):
    """Handle profile form submission with avatar upload support."""
    current_user.full_name = request.form.get('full_name', '').strip()
    current_user.company = request.form.get('company', '').strip()
    current_user.phone = request.form.get('phone', '').strip()
    current_user.bio = request.form.get('bio', '').strip()
    
    new_currency = request.form.get('currency', 'USD').upper()
    if new_currency in CURRENCIES:
        current_user.currency = new_currency

    # Handle avatar upload
    if 'avatar' in request.files:
        file = request.files['avatar']
        if file and file.filename and file.filename.strip():
            try:
                avatar_url = save_uploaded_file(file, 'avatars', 'avatar')
                if avatar_url:
                    # Delete old avatar
                    if current_user.avatar_url:
                        try:
                            old_path = os.path.join(
                                current_app.root_path, 
                                current_user.avatar_url.lstrip('/').replace('/', os.sep)
                            )
                            if os.path.exists(old_path):
                                os.remove(old_path)
                        except Exception as e:
                            current_app.logger.error(f"Error removing old avatar: {e}")
                    
                    current_user.avatar_url = avatar_url
                    flash('Profile photo updated.', 'success')
            except ValueError as e:
                flash(str(e), 'error')
                return redirect(url_for('user.settings', tab='profile'))
            except Exception as e:
                current_app.logger.error(f"Avatar upload error: {e}")
                flash('Failed to upload image. Please try again.', 'error')
                return redirect(url_for('user.settings', tab='profile'))

    # Handle email change
    new_email = request.form.get('email', '').strip().lower()
    if new_email and new_email != current_user.email:
        from models import User
        if User.query.filter_by(email=new_email).first():
            flash('That email address is already in use.', 'error')
            return redirect(url_for('user.settings', tab='profile'))
        current_user.email = new_email

    db.session.commit()
    flash('Profile updated successfully.', 'success')
    return redirect(url_for('user.settings', tab='profile'))

def _handle_security_update(request):
    """Handle password change and 2FA toggle."""
    current_pw = request.form.get('current_password', '')
    new_pw = request.form.get('new_password', '')
    confirm_pw = request.form.get('confirm_password', '')
    two_fa = request.form.get('two_fa') == 'on'

    if new_pw or confirm_pw or current_pw:
        if not check_password_hash(current_user.password_hash, current_pw):
            flash('Current password is incorrect.', 'error')
            return redirect(url_for('user.settings', tab='security'))
        if len(new_pw) < 8:
            flash('New password must be at least 8 characters.', 'error')
            return redirect(url_for('user.settings', tab='security'))
        if new_pw != confirm_pw:
            flash('New passwords do not match.', 'error')
            return redirect(url_for('user.settings', tab='security'))

        current_user.password_hash = generate_password_hash(new_pw)
        flash('Password changed successfully.', 'success')

    if two_fa != current_user.two_fa_enabled:
        if two_fa:
            current_user.two_fa_enabled = True
            flash('Two-factor authentication enabled.', 'success')
        else:
            current_user.two_fa_enabled = False
            current_user.two_fa_secret = None
            flash('Two-factor authentication disabled.', 'success')

    db.session.commit()
    return redirect(url_for('user.settings', tab='security'))

def _handle_notifications_update(request, prefs):
    """Save notification preferences."""
    prefs.email_notif = request.form.get('email_notif') == 'on'
    prefs.sms_notif = request.form.get('sms_notif') == 'on'
    prefs.notif_booking = request.form.get('notif_booking') == 'on'
    prefs.notif_status = request.form.get('notif_status') == 'on'
    prefs.notif_otd = request.form.get('notif_otd') == 'on'
    prefs.notif_delivered = request.form.get('notif_delivered') == 'on'
    prefs.notif_delays = request.form.get('notif_delays') == 'on'
    prefs.notif_news = request.form.get('notif_news') == 'on'
    
    db.session.commit()
    flash('Notification preferences saved.', 'success')
    return redirect(url_for('user.settings', tab='notifications'))

@user_bp.route('/settings/avatar/remove', methods=['POST'])
@login_required
def remove_avatar():
    """Remove user avatar."""
    if current_user.avatar_url:
        try:
            old_path = os.path.join(
                current_app.root_path,
                current_user.avatar_url.lstrip('/').replace('/', os.sep)
            )
            if os.path.exists(old_path):
                os.remove(old_path)
        except Exception as e:
            current_app.logger.error(f"Error removing avatar: {e}")
        
        current_user.avatar_url = None
        db.session.commit()
        flash('Avatar removed.', 'success')
    return redirect(url_for('user.settings', tab='profile'))


@user_bp.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    # Ensure user has a subscription (default to free)
    if not current_user.subscription:
        sub = Subscription(user_id=current_user.id, plan_id='free')
        db.session.add(sub)
        db.session.commit()
    
    notif_prefs = current_user.get_notification_prefs()

    if request.method == 'POST':
        form_type = request.form.get('form_type', 'profile')

        if form_type == 'profile':
            return _handle_profile_update(request)
        elif form_type == 'security':
            return _handle_security_update(request)
        elif form_type == 'notifications':
            return _handle_notifications_update(request, notif_prefs)
    
    active_tab = request.args.get('tab', 'profile')
    
    pending_payment = PaymentRequest.query.filter_by(
        user_id=current_user.id,
        status='pending'
    ).first()
    
    payment_history = PaymentRequest.query.filter(
        PaymentRequest.user_id == current_user.id,
        PaymentRequest.status.in_(['approved', 'rejected'])
    ).order_by(PaymentRequest.created_at.desc()).limit(5).all()
    
    # Get active payment methods (exclude bank_transfer, use bank_transfer_gbp)
    payment_methods = PaymentMethod.query.filter_by(is_active=True).order_by(PaymentMethod.sort_order).all()
    
    return render_template(
        'user/settings.html',
        active_tab=active_tab,
        notif_prefs=notif_prefs,
        plans=PLANS,
        currencies=CURRENCIES,
        subscription=current_user.subscription,
        pending_payment=pending_payment,
        payment_history=payment_history,
        payment_methods=payment_methods,
    )


# @user_bp.route('/settings/payment-method-details/<int:method_id>')
# @login_required
# def get_payment_method_details(method_id):
#     method = PaymentMethod.query.get_or_404(method_id)
#     if not method.is_active:
#         abort(404)
    
#     pending = current_user.get_pending_payment_request()
#     reference = f"UTH-{current_user.id}-{pending.id}" if pending else f"UTH-{current_user.id}-NEW"
#     amount = pending.amount_display if pending else "0.00"
    
#     instructions = method.get_instructions(amount, reference)
    
#     return jsonify({
#         'success': True,
#         'method': {
#             'id': method.id,
#             'name': method.name,
#             'code': method.code,
#             'display_name': method.display_name,
#             'icon': method.icon,
#             'instructions': instructions
#         }
#     })

# ────────────────────────────────────────────
# FIXED: Payment and Plan Upgrade Routes
# ────────────────────────────────────────────

@user_bp.route('/settings/request-plan-change', methods=['POST'])
@login_required
def request_plan_change():
    plan_id = request.form.get('plan_id')
    payment_method_id = request.form.get('payment_method_id')
    
    if not plan_id or plan_id not in PLANS:
        flash('Invalid plan selected.', 'error')
        return redirect(url_for('user.settings', tab='billing'))
    
    current_plan_id = current_user.subscription.plan_id if current_user.subscription else 'free'
    if plan_id == current_plan_id:
        flash('You are already on this plan.', 'info')
        return redirect(url_for('user.settings', tab='billing'))
    
    if plan_id == 'enterprise':
        flash("Please contact sales for Enterprise plan setup.", 'info')
        return redirect(url_for('user.settings', tab='billing'))
    
    # Check for existing pending request
    existing = current_user.get_pending_payment_request()
    if existing:
        flash('You already have a pending payment request. Please complete or cancel it first.', 'info')
        return redirect(url_for('user.settings', tab='billing'))
    
    plan = PLANS[plan_id]
    amount_usd = plan['price_usd'] or 0
    
    # NEW: Check if this is a free downgrade (no payment required)
    if amount_usd == 0:
        # Immediate downgrade to free plan
        if not current_user.subscription:
            sub = Subscription(user_id=current_user.id)
            db.session.add(sub)
        else:
            sub = current_user.subscription
        
        sub.change_plan(plan_id)
        db.session.commit()
        
        flash(f'Successfully downgraded to {plan["name"]} plan.', 'success')
        return redirect(url_for('user.settings', tab='billing'))
    
    # Paid plan - require payment method
    if not payment_method_id:
        flash('Please select a payment method.', 'error')
        return redirect(url_for('user.settings', tab='billing'))
    
    payment_method = PaymentMethod.query.get(payment_method_id)
    if not payment_method or not payment_method.is_active:
        flash('Please select a valid payment method.', 'error')
        return redirect(url_for('user.settings', tab='billing'))
    
    # Create payment request with selected method
    payment_req = PaymentRequest(
        user_id=current_user.id,
        requested_plan_id=plan_id,
        requested_plan_name=plan['name'],
        amount_usd=amount_usd,
        amount_display=current_user.get_plan_price(plan_id),
        payment_method_id=payment_method.id,
        expires_at=datetime.utcnow() + timedelta(days=7)
    )
    
    db.session.add(payment_req)
    db.session.commit()
    
    flash(f'Payment request created. Please complete payment using {payment_method.display_name}.', 'success')
    return redirect(url_for('user.settings', tab='billing'))


@user_bp.route('/settings/upload-payment-proof', methods=['POST'])
@login_required
def upload_payment_proof():
    """Upload payment proof for pending request. FIXED version."""
    payment_id = request.form.get('payment_id')
    payment_req = PaymentRequest.query.filter_by(
        id=payment_id,
        user_id=current_user.id,
        status='pending'
    ).first_or_404()
    
    if 'payment_proof' not in request.files:
        flash('No file provided.', 'error')
        return redirect(url_for('user.settings', tab='billing'))
    
    file = request.files['payment_proof']
    
    try:
        proof_url = save_uploaded_file(file, 'payment_proofs', 'payment')
        if proof_url:
            payment_req.payment_proof_url = proof_url
            payment_req.payment_notes = request.form.get('payment_notes', '').strip()
            db.session.commit()
            flash('Payment proof uploaded successfully. Admin will review shortly.', 'success')
    except ValueError as e:
        flash(str(e), 'error')
    except Exception as e:
        current_app.logger.error(f"Payment proof upload error: {e}")
        flash('Failed to upload payment proof. Please try again.', 'error')
    
    return redirect(url_for('user.settings', tab='billing'))

@user_bp.route('/settings/cancel-payment-request', methods=['POST'])
@login_required
def cancel_payment_request():
    """Cancel pending payment request."""
    payment_id = request.form.get('payment_id')
    payment_req = PaymentRequest.query.filter_by(
        id=payment_id,
        user_id=current_user.id,
        status='pending'
    ).first_or_404()
    
    payment_req.status = 'cancelled'
    db.session.commit()
    
    flash('Payment request cancelled.', 'success')
    return redirect(url_for('user.settings', tab='billing'))


# ────────────────────────────────────────────
# Create Shipment (multi-step)
# ────────────────────────────────────────────

# ────────────────────────────────────────────
# Create Shipment (multi-step with payment)
# ────────────────────────────────────────────

@user_bp.route('/create-shipment', methods=['GET', 'POST'])
@login_required
def create_shipment():
    step = request.args.get('step', '1')

    if request.method == 'POST':
        if step == '1':
            session['origin']         = request.form.get('origin')
            session['destination']    = request.form.get('destination')
            session['sender_name']    = request.form.get('sender_name')
            session['sender_phone']   = request.form.get('sender_phone')
            session['receiver_name']  = request.form.get('receiver_name')
            session['receiver_phone'] = request.form.get('receiver_phone')
            session['receiver_company'] = request.form.get('receiver_company', '')
            return redirect(url_for('user.create_shipment', step='2'))

        elif step == '2':
            packages = []
            files = request.files
            
            i = 1
            while f'length_{i}' in request.form:
                pkg_data = {
                    'length':    request.form.get(f'length_{i}'),
                    'width':     request.form.get(f'width_{i}'),
                    'height':    request.form.get(f'height_{i}'),
                    'weight':    request.form.get(f'weight_{i}'),
                    'description': request.form.get(f'desc_{i}'),
                    'stackable': request.form.get(f'stackable_{i}') == 'on',
                    'fragile':   request.form.get(f'fragile_{i}') == 'on',
                    'images': []  # Will store image URLs
                }
                
                # Handle multiple images for this package
                image_key = f'package_images_{i}'
                if image_key in files:
                    uploaded_files = files.getlist(image_key)
                    for file in uploaded_files:
                        if file and file.filename:
                            try:
                                image_url = save_uploaded_file(file, 'package_images', f'pkg_{i}')
                                pkg_data['images'].append(image_url)
                            except ValueError as e:
                                flash(f'Package {i}: {str(e)}', 'error')
                                return redirect(url_for('user.create_shipment', step='2'))
                
                packages.append(pkg_data)
                i += 1
            
            session['packages']     = packages
            session['total_weight'] = sum(float(p['weight'] or 0) for p in packages)
            return redirect(url_for('user.create_shipment', step='3'))

        elif step == '3':
            session['service'] = request.form.get('service')
            # Calculate cost for payment step
            base_cost = {'Economy': 420, 'Standard': 680, 'Express': 1150}
            session['calculated_cost'] = base_cost.get(session['service'], 420)
            return redirect(url_for('user.create_shipment', step='4'))

        elif step == '4':
            # Payment step - store selected method
            payment_method_id = request.form.get('payment_method_id')
            session['payment_method_id'] = payment_method_id
            return redirect(url_for('user.create_shipment', step='5'))

        elif step == '5':
            # Final confirmation with receipt upload
            service  = session.get('service', 'Standard')
            packages = session.get('packages', [])
            cost = session.get('calculated_cost', 420)
            payment_method_id = session.get('payment_method_id')

            eta_days = {'Economy': 10, 'Standard': 5, 'Express': 2}
            eta = datetime.utcnow() + timedelta(days=eta_days.get(service, 10))

            total_weight = session.get('total_weight', 0)
            dims_summary = (
                f'{len(packages)} package(s)' if len(packages) > 1
                else (
                    f"{packages[0]['length']}×{packages[0]['width']}×{packages[0]['height']} cm"
                    if packages else 'N/A'
                )
            )

            tracking = generate_tracking()
            
            # Create shipment
            shipment = Shipment(
                tracking_number    = tracking,
                user_id            = current_user.id,
                origin             = session.get('origin'),
                destination        = session.get('destination'),
                sender_name        = session.get('sender_name'),
                sender_phone       = session.get('sender_phone'),
                receiver_name      = session.get('receiver_name'),
                receiver_phone     = session.get('receiver_phone'),
                receiver_company   = session.get('receiver_company', ''),
                weight             = total_weight,
                dimensions         = dims_summary,
                commodity          = 'General Cargo',
                service_level      = service,
                cost               = cost,
                status             ='Payment Pending',  # Changed from 'Booking Created'
                estimated_delivery = eta
            )
            db.session.add(shipment)
            db.session.flush()  # Get shipment.id

            # Create packages with images
            for pkg_data in packages:
                p = Package(
                    shipment_id = shipment.id,
                    length      = float(pkg_data.get('length') or 0),
                    width       = float(pkg_data.get('width')  or 0),
                    height      = float(pkg_data.get('height') or 0),
                    weight      = float(pkg_data.get('weight') or 0),
                    description = pkg_data.get('description') or '',
                    stackable   = bool(pkg_data.get('stackable', False)),
                    fragile     = bool(pkg_data.get('fragile',   False)),
                )
                db.session.add(p)
                db.session.flush()  # Get package.id
                
                # Save package images
                for img_url in pkg_data.get('images', []):
                    img = PackageImage(package_id=p.id, image_url=img_url)
                    db.session.add(img)

            # Create payment record
            payment_method = PaymentMethod.query.get(payment_method_id)
            if payment_method:
                payment = ShipmentPayment(
                    shipment_id=shipment.id,
                    user_id=current_user.id,
                    amount=cost,
                    currency='USD',
                    payment_method_id=payment_method.id,
                    status='pending'
                )
                db.session.add(payment)
                db.session.flush()

                # Handle receipt upload
                if 'payment_receipt' in request.files:
                    receipt_file = request.files['payment_receipt']
                    if receipt_file and receipt_file.filename:
                        try:
                            receipt_url = save_uploaded_file(receipt_file, 'payment_receipts', f'shipment_{shipment.id}')
                            payment.receipt_url = receipt_url
                            payment.status = 'pending_verification'  # Awaiting admin approval
                        except ValueError as e:
                            flash(f'Receipt upload error: {str(e)}', 'warning')
                            # Continue without receipt

            # Create initial event
            event = ShipmentEvent(
                shipment_id = shipment.id,
                status      = 'Payment Pending',
                location    = session.get('origin'),
                description = 'Shipment booked. Awaiting payment verification.',
                timestamp   = datetime.utcnow(),
            )
            db.session.add(event)

            db.session.commit()

            # Clear session
            for key in ['origin', 'destination', 'sender_name', 'sender_phone',
                        'receiver_name', 'receiver_phone', 'receiver_company',
                        'packages', 'total_weight', 'service', 'calculated_cost',
                        'payment_method_id']:
                session.pop(key, None)

            flash(f'Shipment {tracking} booked successfully! Please complete payment to proceed.', 'success')
            return redirect(url_for('user.dashboard'))

    templates = {
        '1': 'user/create_shipment/step1.html',
        '2': 'user/create_shipment/step2.html',
        '3': 'user/create_shipment/step3.html',
        '4': 'user/create_shipment/step4.html',  # Payment step
        '5': 'user/create_shipment/step5.html',  # Review & Confirm
    }
    if step not in templates:
        return redirect(url_for('user.create_shipment', step='1'))

    ctx = {}
    if step == '2':
        ctx['max_images'] = 5  # Max images per package
    if step == '3':
        ctx['total_weight'] = session.get('total_weight')

    if step == '4':
        # Get active payment methods with default config
        methods = PaymentMethod.query.filter_by(is_active=True).order_by(PaymentMethod.sort_order).all()
        # Ensure config is never None
        for method in methods:
            if method.config is None:
                method.config = {}
        ctx['payment_methods'] = methods
        ctx['cost'] = session.get('calculated_cost', 420)  # ADD THIS
        ctx['service'] = session.get('service', 'Standard')  # ADD THIS


        ctx['payment_methods'] = methods
    if step == '5':
        ctx['cost'] = session.get('calculated_cost', 420)
        ctx['service'] = session.get('service', 'Standard')
        ctx['payment_method'] = PaymentMethod.query.get(session.get('payment_method_id')) if session.get('payment_method_id') else None

    return render_template(templates[step], **ctx)


# ────────────────────────────────────────────
# Payment Method API (for AJAX loading)
# ────────────────────────────────────────────

@user_bp.route('/api/payment-methods/<int:method_id>')
@login_required
def get_payment_method_details(method_id):
    """Get payment method details for modal"""
    method = PaymentMethod.query.get_or_404(method_id)
    if not method.is_active:
        abort(404)
    
    # Generate unique reference
    reference = f"UTH-SHIP-{current_user.id}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
    
    amount = request.args.get('amount', '0')
    
    return jsonify({
        'success': True,
        'method': {
            'id': method.id,
            'name': method.name,
            'display_name': method.display_name,
            'type': method.method_type,
            'icon': method.icon,
            'instructions': method.get_instructions(amount, reference),
            'reference': reference
        }
    })


@user_bp.route('/api/shipments/<int:shipment_id>/upload-receipt', methods=['POST'])
@login_required
def upload_shipment_receipt(shipment_id):
    """Upload receipt for existing shipment payment"""
    shipment = Shipment.query.get_or_404(shipment_id)
    if shipment.user_id != current_user.id:
        abort(403)
    
    payment = ShipmentPayment.query.filter_by(shipment_id=shipment_id).first()
    if not payment:
        abort(404)
    
    if 'receipt' not in request.files:
        return jsonify({'success': False, 'error': 'No file provided'}), 400
    
    file = request.files['receipt']
    try:
        receipt_url = save_uploaded_file(file, 'payment_receipts', f'shipment_{shipment_id}')
        payment.receipt_url = receipt_url
        payment.status = 'pending_verification'
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Receipt uploaded successfully. Awaiting admin verification.',
            'receipt_url': receipt_url
        })
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        current_app.logger.error(f"Receipt upload error: {e}")
        return jsonify({'success': False, 'error': 'Upload failed'}), 500


# ────────────────────────────────────────────
# JSON API
# ────────────────────────────────────────────

@user_bp.route('/api/shipments')
@login_required
def api_shipments():
    shipments = (
        Shipment.query
        .filter_by(user_id=current_user.id)
        .order_by(Shipment.created_at.desc())
        .all()
    )
    return jsonify(shipments=[shipment_to_dict(s) for s in shipments])

@user_bp.route('/api/shipments/<tracking>')
@login_required
def api_shipment_detail(tracking):
    s = Shipment.query.filter_by(tracking_number=tracking).first_or_404()
    if s.user_id != current_user.id and not current_user.is_admin:
        abort(403)
    return jsonify(shipment_to_dict(s, include_events=True))


# ────────────────────────────────────────────
# Notification Routes
# ────────────────────────────────────────────

@user_bp.route('/notifications')
@login_required
def notifications():
    """Full notification center page."""
    page = request.args.get('page', 1, type=int)
    filter_type = request.args.get('filter', 'all')
    
    query = Notification.query.filter_by(
        user_id=current_user.id,
        is_archived=False
    )
    
    if filter_type == 'unread':
        query = query.filter_by(is_read=False)
    elif filter_type != 'all':
        query = query.filter_by(notification_type=filter_type)
    
    notifications = query.order_by(Notification.created_at.desc()).paginate(
        page=page, per_page=20, error_out=False
    )
    
    # Get unread count
    unread_count = Notification.query.filter_by(
        user_id=current_user.id,
        is_read=False,
        is_archived=False
    ).count()
    
    # Get notification types for filter
    types = db.session.query(Notification.notification_type).filter_by(
        user_id=current_user.id
    ).distinct().all()
    
    return render_template(
        'user/notifications.html',
        notifications=notifications,
        unread_count=unread_count,
        filter_type=filter_type,
        notification_types=[t[0] for t in types]
    )


@user_bp.route('/api/notifications')
@login_required
def api_notifications():
    """Get notifications for dropdown (JSON)."""
    limit = request.args.get('limit', 10, type=int)
    
    notifications = Notification.query.filter_by(
        user_id=current_user.id,
        is_archived=False
    ).order_by(Notification.created_at.desc()).limit(limit).all()
    
    return jsonify({
        'notifications': [{
            'id': n.id,
            'title': n.title,
            'message': n.message,
            'type': n.notification_type,
            'icon': n.icon,
            'color': n.color,
            'is_read': n.is_read,
            'time_ago': n.time_ago,
            'link': n.link,
            'created_at': n.created_at.isoformat()
        } for n in notifications],
        'unread_count': sum(1 for n in notifications if not n.is_read)
    })


@user_bp.route('/api/notifications/unread-count')
@login_required
def unread_count():
    """Get unread notification count."""
    count = Notification.query.filter_by(
        user_id=current_user.id,
        is_read=False,
        is_archived=False
    ).count()
    return jsonify({'count': count})


@user_bp.route('/api/notifications/<int:notification_id>/read', methods=['POST'])
@login_required
def mark_notification_read(notification_id):
    """Mark single notification as read."""
    notification = Notification.query.filter_by(
        id=notification_id,
        user_id=current_user.id
    ).first_or_404()
    
    notification.mark_as_read()
    db.session.commit()
    
    return jsonify({'success': True})


@user_bp.route('/api/notifications/mark-all-read', methods=['POST'])
@login_required
def mark_all_read():
    """Mark all notifications as read."""
    Notification.query.filter_by(
        user_id=current_user.id,
        is_read=False
    ).update({'is_read': True, 'read_at': datetime.utcnow()})
    
    db.session.commit()
    return jsonify({'success': True})


@user_bp.route('/api/notifications/<int:notification_id>/archive', methods=['POST'])
@login_required
def archive_notification(notification_id):
    """Archive a notification."""
    notification = Notification.query.filter_by(
        id=notification_id,
        user_id=current_user.id
    ).first_or_404()
    
    notification.is_archived = True
    db.session.commit()
    
    return jsonify({'success': True})


# @user_bp.route('/notifications/stream')
# @login_required
# def notification_stream():
#     """Server-Sent Events endpoint for real-time notifications."""
#     def event_stream():
#         from flask import stream_with_context
        
#         last_check = datetime.utcnow()
        
#         while True:
#             # Check for new notifications
#             new_notifications = Notification.query.filter(
#                 Notification.user_id == current_user.id,
#                 Notification.created_at > last_check,
#                 Notification.is_archived == False
#             ).all()
            
#             if new_notifications:
#                 for notif in new_notifications:
#                     data = {
#                         'id': notif.id,
#                         'title': notif.title,
#                         'message': notif.message,
#                         'type': notif.notification_type,
#                         'icon': notif.icon,
#                         'color': notif.color,
#                         'time_ago': notif.time_ago,
#                         'link': notif.link
#                     }
#                     yield f"data: {json.dumps(data)}\n\n"
                
#                 last_check = datetime.utcnow()
            
#             # Send heartbeat every 30 seconds
#             yield f":heartbeat\n\n"
#             import time
#             time.sleep(30)
    
#     from flask import Response
#     return Response(
#         stream_with_context(event_stream()),
#         mimetype='text/event-stream',
#         headers={
#             'Cache-Control': 'no-cache',
#             'X-Accel-Buffering': 'no'
#         }
#     )

@user_bp.route('/notifications/stream')
@login_required
def notification_stream():
    """Replaced with polling — SSE breaks PostgreSQL connections."""
    def empty_stream():
        yield ": keep-alive\n\n"
    
    return Response(
        empty_stream(),
        mimetype='text/event-stream',
        headers={'Cache-Control': 'no-cache'}
    )

# ────────────────────────────────────────────
# Helper: Create Notification
# ────────────────────────────────────────────

def create_notification(user_id, title, message, notification_type, 
                       related_shipment_id=None, related_ticket_id=None, 
                       link=None, priority='normal'):
    """Helper function to create notifications."""
    notification = Notification(
        user_id=user_id,
        title=title,
        message=message,
        notification_type=notification_type,
        related_shipment_id=related_shipment_id,
        related_ticket_id=related_ticket_id,
        link=link,
        priority=priority
    )
    db.session.add(notification)
    db.session.commit()
    return notification