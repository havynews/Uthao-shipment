"""
admin.py — UTHAO Admin Blueprint
Full administrative control panel with user impersonation
"""

from flask import (
    Blueprint, render_template, redirect, url_for, flash, 
    request, jsonify, abort, session, current_app
)
from flask_login import login_required, current_user, login_user, logout_user
from functools import wraps
from datetime import datetime, timedelta, date
from sqlalchemy import func
import json
import os
from models import (
    User, Shipment, ShipmentEvent, Package, Subscription, 
    PaymentRequest, PaymentMethod, SupportTicket, TicketReply, ShipmentPayment,
    Notification, Plan, PLANS, CURRENCIES
)

from extensions import db, mail, login_manager, migrate
from models import ShipmentPayment, Notification, PackageImage, Package
from decorators import with_db_retry

from notification import create_notification
from sqlalchemy.orm import joinedload  # Add this import at the top
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
from sqlalchemy.orm import joinedload
import base64


admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

# ────────────────────────────────────────────
# Decorators
# ────────────────────────────────────────────


# Configure Cloudinary (add to your app initialization)
cloudinary.config(
    cloud_name=os.environ.get('CLOUDINARY_CLOUD_NAME'),
    api_key=os.environ.get('CLOUDINARY_API_KEY'),
    api_secret=os.environ.get('CLOUDINARY_API_SECRET')
)


smtp_server = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
smtp_port = int(os.environ.get('MAIL_PORT', 587))
smtp_username = os.environ.get('MAIL_USERNAME')
smtp_password = os.environ.get('MAIL_PASSWORD')
sender_email = os.environ.get('SENDER_EMAIL', smtp_username)
sender_name = os.environ.get('SENDER_NAME', 'UTHAO Logistics')

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            abort(401)  # Not logged in
        
        if not current_user.is_admin:
            abort(403)  # Forbidden
        
        return f(*args, **kwargs)
    return decorated_function


def super_admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            abort(403)
        # Check if super admin (first admin or specific flag)
        if current_user.id != 1 and not getattr(current_user, 'is_super_admin', False):
            abort(403, description="Super admin access required")
        return f(*args, **kwargs)
    return decorated_function


from flask import (
    Blueprint, render_template, redirect, url_for, flash, 
    request, jsonify, abort, session, current_app, g
)



ALLOWED_TYPES = {
    'system', 'billing', 'shipment', 'promotional', 'security', 'support',
    'shipment_delivered', 'shipment_transit', 'payment_success',
    'payment_failed', 'plan_change', 'ticket_reply',
}

ALLOWED_PRIORITIES = {'low', 'normal', 'high', 'urgent'}


@admin_bp.app_template_global()
def get_status_color(status):
    """Return color code for shipment status."""
    colors = {
        'Delivered': '#22c55e',
        'Out for Delivery': '#8b5cf6',
        'In Transit': '#f97316',
        'Picked Up': '#3b82f6',
        'Arrived at Hub': '#d97706',
        'Customs Clearance': '#f59e0b',
        'On Hold': '#6b7280',
        'Cancelled': '#ef4444',
        'Booking Created': '#2563eb',
        'Pending Payment': '#eab308',
    }
    return colors.get(status, '#6b7280')


# Add this before your routes
@admin_bp.before_request
@login_required
@admin_required
def inject_sidebar_stats():
    """Inject stats for sidebar notifications."""
    from sqlalchemy import func
    from datetime import datetime, timedelta
    
    g.pending_payments = PaymentRequest.query.filter_by(status='pending').count()
    g.open_tickets = SupportTicket.query.filter_by(status='open').count()
    g.pending_shipment_payments = ShipmentPayment.query.filter(
        ShipmentPayment.status.in_(['pending', 'pending_verification'])
    ).count()

# ────────────────────────────────────────────
# Dashboard
# ────────────────────────────────────────────

@admin_bp.route('/dashboard')
@login_required
@admin_required
def dashboard():
    """Admin dashboard with overview statistics."""
    
    # Date ranges
    today = datetime.utcnow()
    thirty_days_ago = today - timedelta(days=30)
    seven_days_ago = today - timedelta(days=7)
    
    # Key metrics
    total_users = User.query.count()
    new_users_this_month = User.query.filter(User.created_at >= thirty_days_ago).count()
    
    total_shipments = Shipment.query.count()
    shipments_this_month = Shipment.query.filter(Shipment.created_at >= thirty_days_ago).count()
    active_shipments = Shipment.query.filter(
        ~Shipment.status.in_(['Delivered', 'Cancelled'])
    ).count()
    
    # Revenue calculation
    total_revenue = db.session.query(func.sum(PaymentRequest.amount_usd)).filter(
        PaymentRequest.status == 'approved'
    ).scalar() or 0
    
    revenue_this_month = db.session.query(func.sum(PaymentRequest.amount_usd)).filter(
        PaymentRequest.status == 'approved',
        PaymentRequest.reviewed_at >= thirty_days_ago
    ).scalar() or 0
    
    # Pending actions
    pending_payments = PaymentRequest.query.filter_by(status='pending').count()
    open_tickets = SupportTicket.query.filter_by(status='open').count()
    
    # Recent activity
    recent_users = User.query.order_by(User.id.desc()).limit(5).all()
    recent_shipments = Shipment.query.order_by(Shipment.created_at.desc()).limit(5).all()
    recent_payments = PaymentRequest.query.order_by(PaymentRequest.created_at.desc()).limit(5).all()
    
    # Chart data
    daily_shipments = db.session.query(
        func.date(Shipment.created_at),
        func.count(Shipment.id)
    ).filter(
        Shipment.created_at >= thirty_days_ago
    ).group_by(func.date(Shipment.created_at)).all()
    
    # chart_labels = [
    #     datetime.strptime(d[0], '%Y-%m-%d').strftime('%d %b')
    #     if d[0] else ''
    #     for d in daily_shipments
    # ]

    chart_labels = [
        (d[0].strftime('%d %b') if isinstance(d[0], date) else datetime.strptime(d[0], '%Y-%m-%d').strftime('%d %b'))
        if d[0] else ''
        for d in daily_shipments
    ]

    chart_data = [d[1] for d in daily_shipments]
    
    return render_template(
        'admin/dashboard.html',
        stats={
            'total_users': total_users,
            'new_users_this_month': new_users_this_month,
            'total_shipments': total_shipments,
            'shipments_this_month': shipments_this_month,
            'active_shipments': active_shipments,
            'total_revenue': total_revenue,
            'revenue_this_month': revenue_this_month,
            'pending_payments': pending_payments,
            'open_tickets': open_tickets
        },
        recent_users=recent_users,
        recent_shipments=recent_shipments,
        recent_payments=recent_payments,
        chart_labels=chart_labels,
        chart_data=chart_data
    )


# ────────────────────────────────────────────
# User Management
# ────────────────────────────────────────────

@admin_bp.route('/users')
@login_required
@admin_required
def users():
    """List all users with search and filter."""
    page = request.args.get('page', 1, type=int)
    search = request.args.get('q', '').strip()
    plan_filter = request.args.get('plan', '').strip()
    
    query = User.query
    
    if search:
        query = query.filter(
            db.or_(
                User.email.ilike(f'%{search}%'),
                User.full_name.ilike(f'%{search}%'),
                User.company.ilike(f'%{search}%')
            )
        )
    
    if plan_filter:
        query = query.join(Subscription).filter(Subscription.plan_id == plan_filter)
    
    users = query.order_by(User.id.desc()).paginate(
        page=page, per_page=20, error_out=False
    )
    
    return render_template(
        'admin/users.html',
        users=users,
        plans=PLANS,
        search=search,
        plan_filter=plan_filter
    )

@admin_bp.route('/users/<int:user_id>')
@login_required
@admin_required
def user_detail(user_id):
    """View detailed user information."""
    user = User.query.get_or_404(user_id)
    
    # Get user stats
    shipment_count = Shipment.query.filter_by(user_id=user.id).count()
    total_spent = db.session.query(func.sum(Shipment.cost)).filter_by(
        user_id=user.id
    ).scalar() or 0
    
    recent_shipments = Shipment.query.filter_by(
        user_id=user.id
    ).order_by(Shipment.created_at.desc()).limit(10).all()
    
    tickets = SupportTicket.query.filter_by(
        user_id=user.id
    ).order_by(SupportTicket.created_at.desc()).limit(10).all()
    
    payment_history = PaymentRequest.query.filter_by(
        user_id=user.id
    ).order_by(PaymentRequest.created_at.desc()).all()
    
    return render_template(
        'admin/user_detail.html',
        user=user,
        stats={
            'shipment_count': shipment_count,
            'total_spent': total_spent
        },
        recent_shipments=recent_shipments,
        tickets=tickets,
        payment_history=payment_history,
        plans=PLANS
    )

@admin_bp.route('/users/<int:user_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_user(user_id):
    """Edit user details."""
    user = User.query.get_or_404(user_id)
    
    if request.method == 'POST':
        user.full_name = request.form.get('full_name', '').strip()
        user.email = request.form.get('email', '').strip().lower()
        user.company = request.form.get('company', '').strip()
        user.phone = request.form.get('phone', '').strip()
        user.is_admin = request.form.get('is_admin') == 'on'
        user.currency = request.form.get('currency', 'USD')
        
        # Handle plan change
        new_plan = request.form.get('plan_id')
        if new_plan and new_plan in PLANS:
            if not user.subscription:
                sub = Subscription(user_id=user.id, plan_id=new_plan)
                db.session.add(sub)
            else:
                user.subscription.change_plan(new_plan)
        
        db.session.commit()
        flash(f'User {user.email} updated successfully.', 'success')
        return redirect(url_for('admin.user_detail', user_id=user.id))
    
    return render_template('admin/edit_user.html', user=user, plans=PLANS, currencies=CURRENCIES)


@admin_bp.route('/users/<int:user_id>/send-notification', methods=['POST'])
@login_required
def send_user_notification(user_id):
    """
    Admin action: compose and send a notification to a specific user.

    Expected POST fields (from edit_user.html notification tab):
        notification_type  – one of ALLOWED_TYPES          (default: 'system')
        priority           – one of ALLOWED_PRIORITIES      (default: 'normal')
        title              – str, 1-120 chars               (required)
        message            – str, 1-500 chars               (required)
        link               – optional URL the notification links to
    """
    # ── Guard: admin only ──────────────────────────────────────────────────────
    if not current_user.is_admin:
        abort(403)

    # ── Fetch target user ──────────────────────────────────────────────────────
    user = User.query.get_or_404(user_id)

    # ── Pull & sanitise form data ──────────────────────────────────────────────
    notification_type = request.form.get('notification_type', 'system').strip().lower()
    priority          = request.form.get('priority', 'normal').strip().lower()
    title             = request.form.get('title', '').strip()
    message           = request.form.get('message', '').strip()
    link              = request.form.get('link', '').strip() or None

    # ── Validation ─────────────────────────────────────────────────────────────
    errors = []

    if not title:
        errors.append('Title is required.')
    elif len(title) > 120:
        errors.append('Title must be 120 characters or fewer.')

    if not message:
        errors.append('Message is required.')
    elif len(message) > 500:
        errors.append('Message must be 500 characters or fewer.')

    if notification_type not in ALLOWED_TYPES:
        notification_type = 'system'          # silently fall back to safe default

    if priority not in ALLOWED_PRIORITIES:
        priority = 'normal'

    if errors:
        for err in errors:
            flash(err, 'error')
        return redirect(url_for('admin.edit_user', user_id=user_id) + '#notify')

    # ── Create the notification ────────────────────────────────────────────────
    try:
        notification = create_notification(
            user_id=user.id,
            title=title,
            message=message,
            notification_type=notification_type,
            link=link,
            priority=priority,
        )

        # ── Audit log (optional but recommended) ───────────────────────────────
        # If you have an AdminAuditLog model you can record this action:
        #
        # AdminAuditLog.log(
        #     admin_id=current_user.id,
        #     action='send_notification',
        #     target_user_id=user.id,
        #     detail=f'[{priority.upper()}] {notification_type}: {title}',
        # )
        # db.session.commit()

        flash(
            f'Notification sent to {user.full_name or user.email} successfully.',
            'success',
        )

    except Exception as exc:
        db.session.rollback()
        # Log the real error server-side but show a friendly message
        current_app.logger.error(
            f'Failed to send notification to user {user_id}: {exc}', exc_info=True
        )
        flash('Failed to send notification. Please try again.', 'error')

    return redirect(url_for('admin.edit_user', user_id=user_id))



@admin_bp.route('/users/<int:user_id>/toggle-admin', methods=['POST'])
@login_required
@super_admin_required
def toggle_admin(user_id):
    """Toggle admin status (super admin only)."""
    user = User.query.get_or_404(user_id)
    
    # Prevent self-demotion
    if user.id == current_user.id:
        flash('You cannot modify your own admin status.', 'error')
        return redirect(url_for('admin.user_detail', user_id=user.id))
    
    user.is_admin = not user.is_admin
    db.session.commit()
    
    status = 'granted' if user.is_admin else 'revoked'
    flash(f'Admin access {status} for {user.email}.', 'success')
    return redirect(url_for('admin.user_detail', user_id=user.id))

@admin_bp.route('/users/<int:user_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_user(user_id):
    """Permanently delete user account (super admin only)."""
    
    user = User.query.get_or_404(user_id)

    # Prevent self-deletion
    if user.id == current_user.id:
        flash('You cannot delete your own account.', 'error')
        return redirect(url_for('admin.users'))

    # Optional: Prevent deleting other admins
    if user.is_admin:
        flash('You cannot delete another admin account.', 'error')
        return redirect(url_for('admin.users'))

    try:
        db.session.delete(user)
        db.session.commit()

        flash(f'User {user.full_name} has been permanently deleted.', 'success')

    except Exception as e:
        db.session.rollback()
        flash('An error occurred while deleting the user.', 'error')

    return redirect(url_for('admin.users'))


@admin_bp.route('/user/<int:user_id>/toggle-status', methods=['POST'])
@login_required
@admin_required
def toggle_user_status(user_id):
    user = User.query.get_or_404(user_id)

    # Prevent admin from disabling themselves
    if user.id == current_user.id:
        flash("You cannot modify your own account status.", "danger")
        return redirect(url_for('admin.view_user', user_id=user.id))

    # Toggle status
    user.is_active = not user.is_active
    db.session.commit()

    if user.is_active:
        flash("User account has been activated successfully.", "success")
    else:
        flash("User account has been deactivated successfully.", "warning")

    return redirect(url_for('admin.user_detail', user_id=user.id))


# ────────────────────────────────────────────
# IMPERSONATION: Login as User
# ────────────────────────────────────────────

@admin_bp.route('/users/<int:user_id>/impersonate', methods=['POST'])
@login_required
def impersonate_user(user_id):
    """Login as another user for support/debugging."""
    if session.get('impersonator_id'):
        flash('You are already impersonating a user.', 'error')
        return redirect(url_for('admin.users'))
    
    target_user = User.query.get_or_404(user_id)
    
    # Store original admin ID
    session['impersonator_id'] = current_user.id
    session['impersonator_name'] = current_user.full_name
    
    # Log the action
    current_app.logger.info(
        f"Admin {current_user.email} impersonating user {target_user.email}"
    )
    
    # Login as target user
    logout_user()
    login_user(target_user, remember=False)
    
    flash(f'You are now logged in as {target_user.full_name} ({target_user.email}). '
          f'Click "Return to Admin" in the top bar to exit.', 'warning')
    
    return redirect(url_for('user.dashboard'))

@admin_bp.route('/stop-impersonating')
def stop_impersonating():
    """Return to admin account."""
    impersonator_id = session.get('impersonator_id')
    
    if not impersonator_id:
        flash('No active impersonation session.', 'error')
        return redirect(url_for('user.dashboard'))
    
    admin_user = User.query.get(impersonator_id)
    if not admin_user or not admin_user.is_admin:
        flash('Admin account not found.', 'error')
        return redirect(url_for('user.dashboard'))
    
    # Clear impersonation data
    session.pop('impersonator_id', None)
    session.pop('impersonator_name', None)
    
    # Return to admin
    logout_user()
    login_user(admin_user, remember=True)
    
    flash('Returned to admin account.', 'success')
    return redirect(url_for('admin.dashboard'))

# ────────────────────────────────────────────
# Shipment Management
# ────────────────────────────────────────────

@admin_bp.route('/shipments')
@login_required
@admin_required
def shipments():
    """View and manage all shipments."""
    page = request.args.get('page', 1, type=int)
    status_filter = request.args.get('status', '').strip()
    search = request.args.get('q', '').strip()
    
    query = Shipment.query
    
    if status_filter:
        query = query.filter_by(status=status_filter)
    
    if search:
        query = query.filter(
            db.or_(
                Shipment.tracking_number.ilike(f'%{search}%'),
                Shipment.origin.ilike(f'%{search}%'),
                Shipment.destination.ilike(f'%{search}%')
            )
        )
    
    shipments = query.order_by(Shipment.created_at.desc()).paginate(
        page=page, per_page=20, error_out=False
    )
    
    # Get status counts for filter
    status_counts = db.session.query(
        Shipment.status,
        func.count(Shipment.id)
    ).group_by(Shipment.status).all()
    
    return render_template(
        'admin/shipments.html',
        shipments=shipments,
        status_counts=dict(status_counts),
        status_filter=status_filter,
        search=search
    )

# @admin_bp.route('/shipments/<int:shipment_id>')
# @login_required
# @admin_required
# def shipment_detail(shipment_id):
#     """View shipment details."""
#     shipment = Shipment.query.options(
#         joinedload(Shipment.customer),
#         joinedload(Shipment.packages),
#         joinedload(Shipment.events)
#     ).get_or_404(shipment_id)
#     return render_template('admin/shipment_detail.html', shipment=shipment)

# @admin_bp.route('/shipments/<int:shipment_id>/update-status', methods=['POST'])
# @login_required
# @admin_required
# def update_shipment_status(shipment_id):
#     """Update shipment status and notify user."""
#     shipment = Shipment.query.get_or_404(shipment_id)
    
#     new_status = request.form.get('status')
#     location = request.form.get('location', '').strip()
#     description = request.form.get('description', '').strip()
    
#     if not new_status:
#         flash('Status is required.', 'error')
#         return redirect(url_for('admin.shipment_detail', shipment_id=shipment.id))
    
#     old_status = shipment.status
#     shipment.status = new_status
    
#     # Add event
#     event = ShipmentEvent(
#         shipment_id=shipment.id,
#         status=new_status,
#         location=location,
#         description=description or f'Status updated to {new_status}',
#         timestamp=datetime.utcnow()
#     )
#     db.session.add(event)
    
#     # Create notification for user
#     notification = Notification(
#         user_id=shipment.user_id,
#         title=f'Shipment {new_status}',
#         message=f'Your shipment {shipment.tracking_number} is now {new_status}.',
#         notification_type=f'shipment_{new_status.lower().replace(" ", "_")}',
#         related_shipment_id=shipment.id,
#         link=f'/tracking?q={shipment.tracking_number}',
#         priority='high' if new_status == 'Delivered' else 'normal'
#     )
#     db.session.add(notification)
    
#     db.session.commit()
    
#     flash(f'Shipment status updated to {new_status}.', 'success')
#     return redirect(url_for('admin.shipment_detail', shipment_id=shipment.id))


@admin_bp.route('/shipments/<int:shipment_id>/update-status', methods=['POST'])
@login_required
@admin_required
def update_shipment_status(shipment_id):
    """Update shipment status and notify user."""
    # Eager load the customer relationship to ensure it's available
    shipment = Shipment.query.options(
        joinedload(Shipment.customer)
    ).get_or_404(shipment_id)
    
    new_status = request.form.get('status')
    location = request.form.get('location', '').strip()
    description = request.form.get('description', '').strip()
    notify_user = request.form.get('notify_user') == 'on'

    # Debug prints
    print(f'Form data: {dict(request.form)}')
    print(f'notify_user raw: {request.form.get("notify_user")}')
    print(f'notify_user bool: {notify_user}')
    print(f'shipment.user_id: {shipment.user_id}')
    print(f'shipment.customer: {shipment.customer}')
    if shipment.customer:
        print(f'shipment.customer.email: {shipment.customer.email}')
    else:
        print('CUSTOMER IS NONE - attempting to load manually...')
        # Fallback: manually load the user if relationship failed
        customer = User.query.get(shipment.user_id)
        print(f'Manually loaded customer: {customer}')
        if customer:
            shipment.customer = customer  # Attach for email function

    if not new_status:
        flash('Status is required.', 'error')
        return redirect(url_for('admin.shipment_detail', shipment_id=shipment.id))
    
    old_status = shipment.status
    shipment.status = new_status

    # Update ETA if provided
    new_eta = request.form.get('estimated_delivery')
    if new_eta:
        from datetime import datetime
        shipment.estimated_delivery = datetime.strptime(new_eta, '%Y-%m-%d')
    
    # Add tracking event
    event = ShipmentEvent(
        shipment_id=shipment.id,
        status=new_status,
        location=location,
        description=description or f'Status updated to {new_status}',
        timestamp=datetime.utcnow()
    )
    db.session.add(event)
    
    # In-app notification
    notification = Notification(
        user_id=shipment.user_id,
        title=f'Shipment {new_status}',
        message=f'Your shipment {shipment.tracking_number} is now {new_status}.',
        notification_type=f'shipment_{new_status.lower().replace(" ", "_")}',
        related_shipment_id=shipment.id,
        link=f'/tracking?q={shipment.tracking_number}',
        priority='high' if new_status == 'Delivered' else 'normal'
    )
    db.session.add(notification)
    db.session.commit()

    # Send email via Mailjet
    if notify_user:
        if not shipment.customer:
            current_app.logger.error(f'Shipment {shipment.id} has no customer (user_id: {shipment.user_id})')
            flash('Status updated but customer not found for email notification.', 'warning')
        elif not shipment.customer.email:
            current_app.logger.warning(f'Customer {shipment.customer.id} has no email')
            flash('Status updated but customer has no email address.', 'warning')
        else:
            try:
                _send_status_email(shipment, new_status, location, description)
                flash(f'Email notification sent to {shipment.customer.email}.', 'success')
            except Exception as e:
                current_app.logger.error(f'Email failed: {e}', exc_info=True)
                flash('Status updated but email notification failed.', 'warning')
    
    flash(f'Shipment status updated to {new_status}.', 'success')
    return redirect(url_for('admin.shipment_detail', shipment_id=shipment.id))


@admin_bp.route('/shipments/<int:shipment_id>/preview-email', methods=['POST'])
@login_required
@admin_required
def preview_email(shipment_id):
    """Preview email before sending."""
    
    shipment = Shipment.query.options(
        joinedload(Shipment.customer),
        joinedload(Shipment.packages).joinedload(Package.images)
    ).get_or_404(shipment_id)
    
    new_status = request.form.get('status', 'In Transit')
    location = request.form.get('location', '').strip()
    description = request.form.get('description', '').strip()
    selected_image_id = request.form.get('selected_image_id')
    
    customer = shipment.customer or User.query.get(shipment.user_id)
    
    # Get image URL if selected
    image_url = None
    if selected_image_id:
        for pkg in shipment.packages:
            for img in pkg.images:
                if str(img.id) == selected_image_id:
                    image_url = img.image_url
                    break
    
    # Generate email content
    base_url = os.environ.get('APP_BASE_URL', 'https://uthao-shipment.onrender.com')
    tracking_path = os.environ.get('TRACKING_URL_PATH', '/tracking/details/')
    tracking_url = f"{base_url.rstrip('/')}{tracking_path}{shipment.tracking_number}"
    
    status_config = {
        'Delivered': {'color': '#22c55e', 'emoji': '✅'},
        'Out for Delivery': {'color': '#8b5cf6', 'emoji': '🚚'},
        'In Transit': {'color': '#f97316', 'emoji': '📦'},
        'Picked Up': {'color': '#3b82f6', 'emoji': '📋'},
        'Arrived at Hub': {'color': '#d97706', 'emoji': '🏭'},
        'Customs Clearance': {'color': '#f59e0b', 'emoji': '🛃'},
        'On Hold': {'color': '#6b7280', 'emoji': '⏸️'},
        'Cancelled': {'color': '#ef4444', 'emoji': '❌'},
    }
    config = status_config.get(new_status, {'color': '#f97316', 'emoji': '📦'})
    
    preview_data = {
        'subject': f'{config["emoji"]} Shipment {shipment.tracking_number} — {new_status}',
        'tracking_number': shipment.tracking_number,  # <-- ADD THIS
        'to': customer.email if customer else 'No email',
        'to_name': customer.full_name if customer else 'Unknown',
        'tracking_url': tracking_url,
        'status': new_status,
        'color': config['color'],
        'emoji': config['emoji'],
        'image_url': image_url,
        'location': location,
        'description': description,
        'has_image': bool(image_url)
    }
    
    return jsonify(preview_data)


def log_email(user_id, shipment_id, email_type, subject, recipient_email, 
              status='sent', status_sent=None, included_image=False, 
              error_message=None):
    """Log email to database."""
    try:
        log = EmailLog(
            user_id=user_id,
            shipment_id=shipment_id,
            email_type=email_type,
            subject=subject,
            recipient_email=recipient_email,
            status=status,
            status_sent=status_sent,
            included_image=included_image,
            error_message=error_message
        )
        db.session.add(log)
        db.session.commit()
    except Exception as e:
        current_app.logger.error(f'Failed to log email: {e}')
        db.session.rollback()

def send_smtp_email_with_retry(to_email, to_name, subject, html_body, text_body, 
                                image_url=None, image_cid=None, max_retries=2):
    """Send email via SMTP with retry logic."""
    
    if not smtp_username or not smtp_password:
        raise ValueError('SMTP credentials not configured')
    
    # Create message
    msg = MIMEMultipart('related')
    msg['Subject'] = subject
    msg['From'] = f'{sender_name} <{sender_email}>'
    msg['To'] = f'{to_name} <{to_email}>' if to_name else to_email
    
    # Anti-spam headers
    msg['X-Mailer'] = 'UTHAO Logistics System v1.0'
    msg['X-Priority'] = '3'
    msg['Precedence'] = 'bulk'
    msg['Auto-Submitted'] = 'auto-generated'
    
    # List-Unsubscribe header (improves deliverability)
    msg['List-Unsubscribe'] = f'<mailto:unsubscribe@uthao.com?subject=unsubscribe-{to_email}>'
    
    # Create alternative part for text/html
    msg_alternative = MIMEMultipart('alternative')
    msg.attach(msg_alternative)
    
    # Attach plain text first (important for spam filters)
    msg_alternative.attach(MIMEText(text_body, 'plain', 'utf-8'))
    msg_alternative.attach(MIMEText(html_body, 'html', 'utf-8'))
    
    # Attach image if provided
    if image_url and image_cid:
        image_data = download_image_for_attachment(image_url)
        if image_data:
            # Detect image type
            image_type = 'jpeg'
            if '.png' in image_url.lower():
                image_type = 'png'
            elif '.gif' in image_url.lower():
                image_type = 'gif'
            elif '.webp' in image_url.lower():
                image_type = 'webp'
            
            image = MIMEImage(image_data, _subtype=image_type)
            image.add_header('Content-ID', f'<{image_cid}>')
            image.add_header('Content-Disposition', 'inline', filename=f'package.{image_type}')
            msg.attach(image)
    
    # Send with retry
    last_error = None
    for attempt in range(max_retries + 1):
        try:
            with smtplib.SMTP(smtp_server, smtp_port, timeout=30) as server:
                server.starttls()
                server.login(smtp_username, smtp_password)
                server.send_message(msg)
            
            current_app.logger.info(f'SMTP email sent to {to_email} (attempt {attempt + 1})')
            return True, None
            
        except Exception as e:
            last_error = str(e)
            current_app.logger.warning(f'SMTP attempt {attempt + 1} failed: {e}')
            if attempt < max_retries:
                import time
                time.sleep(2 ** attempt)  # Exponential backoff
    
    return False, last_error


def get_cloudinary_image(image_public_id, width=600):
    """Get image URL from Cloudinary or download for email attachment."""
    try:
        if not image_public_id:
            return None
            
        # Generate optimized URL
        url = cloudinary.CloudinaryImage(image_public_id).build_url(
            width=width,
            crop='scale',
            quality='auto',
            fetch_format='auto'
        )
        return url
    except Exception as e:
        current_app.logger.error(f'Cloudinary error: {e}')
        return None

def download_image_for_attachment(image_url):
    """Download image from URL for email attachment."""
    try:
        response = requests.get(image_url, timeout=10)
        if response.status_code == 200:
            return response.content
        return None
    except Exception as e:
        current_app.logger.error(f'Image download error: {e}')
        return None

def send_smtp_email(to_email, to_name, subject, html_body, text_body, 
                    image_url=None, image_cid=None):
    """Send email via SMTP with optional embedded image."""
    
    if not smtp_username or not smtp_password:
        current_app.logger.error('SMTP credentials not configured')
        raise ValueError('SMTP credentials not configured')
    
    # Create message
    msg = MIMEMultipart('related')
    msg['Subject'] = subject
    msg['From'] = f'{sender_name} <{sender_email}>'
    msg['To'] = f'{to_name} <{to_email}>' if to_name else to_email
    
    # Add headers to improve deliverability
    msg['X-Mailer'] = 'UTHAO Logistics System'
    msg['X-Priority'] = '3'
    
    # Create alternative part for text/html
    msg_alternative = MIMEMultipart('alternative')
    msg.attach(msg_alternative)
    
    # Attach plain text
    msg_alternative.attach(MIMEText(text_body, 'plain', 'utf-8'))
    
    # Attach HTML
    msg_alternative.attach(MIMEText(html_body, 'html', 'utf-8'))
    
    # Attach image if provided
    if image_url and image_cid:
        image_data = download_image_for_attachment(image_url)
        if image_data:
            image = MIMEImage(image_data)
            image.add_header('Content-ID', f'<{image_cid}>')
            image.add_header('Content-Disposition', 'inline', filename='package.jpg')
            msg.attach(image)
            current_app.logger.info(f'Image attached: {image_cid}')
    
    # Send email
    try:
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(smtp_username, smtp_password)
            server.send_message(msg)
        
        current_app.logger.info(f'SMTP email sent to {to_email}')
        return True
        
    except Exception as e:
        current_app.logger.error(f'SMTP error: {e}')
        raise

@admin_bp.route('/shipments/<int:shipment_id>')
@login_required
@admin_required
def shipment_detail(shipment_id):
    """View shipment details."""
    shipment = Shipment.query.options(
        joinedload(Shipment.customer),
        joinedload(Shipment.packages).joinedload(Package.images),
        joinedload(Shipment.events)
    ).get_or_404(shipment_id)
    
    # Collect all images from all packages for the template
    all_images = []
    for pkg in shipment.packages:
        for img in pkg.images:
            all_images.append({
                'id': img.id,
                'url': img.image_url,
                'package_id': pkg.id,
                'package_index': shipment.packages.index(pkg) + 1
            })
    
    return render_template('admin/shipment_detail.html', 
                         shipment=shipment, 
                         available_images=all_images)


@admin_bp.route('/shipments/bulk-update', methods=['GET', 'POST'])
@login_required
@admin_required
def bulk_update_shipments():
    """
    Enhanced bulk shipment update with:
    - Status updates with optional images
    - Email notifications with preview
    - Progress tracking
    - CSV export of results
    """
    
    if request.method == 'POST':
        action = request.form.get('bulk_action', 'update')
        
        # Handle different actions
        if action == 'preview_email':
            return preview_bulk_email()
        elif action == 'update':
            return process_bulk_update()
        elif action == 'delete':
            return process_bulk_delete()
        
        flash('Invalid action specified.', 'error')
        return redirect(url_for('admin.bulk_update_shipments'))
    
    # GET request - show bulk update interface
    # Get filter parameters
    status_filter = request.args.get('status', '').strip()
    date_from = request.args.get('date_from', '').strip()
    date_to = request.args.get('date_from', '').strip()
    search = request.args.get('q', '').strip()
    page = request.args.get('page', 1, type=int)
    
    # Build query
    query = Shipment.query.options(
        joinedload(Shipment.customer),
        joinedload(Shipment.packages).joinedload(Package.images),
        joinedload(Shipment.events)
    )
    
    # Apply filters
    if status_filter:
        query = query.filter_by(status=status_filter)
    if search:
        query = query.filter(
            db.or_(
                Shipment.tracking_number.ilike(f'%{search}%'),
                Shipment.origin.ilike(f'%{search}%'),
                Shipment.destination.ilike(f'%{search}%'),
                Shipment.customer.has(User.email.ilike(f'%{search}%'))
            )
        )
    if date_from:
        try:
            from_date = datetime.strptime(date_from, '%Y-%m-%d')
            query = query.filter(Shipment.created_at >= from_date)
        except ValueError:
            pass
    if date_to:
        try:
            to_date = datetime.strptime(date_to, '%Y-%m-%d')
            query = query.filter(Shipment.created_at <= to_date + timedelta(days=1))
        except ValueError:
            pass
    
    # Get paginated results
    shipments = query.order_by(Shipment.created_at.desc()).paginate(
        page=page, per_page=50, error_out=False
    )
    
    # Get all status options for dropdown
    all_statuses = db.session.query(Shipment.status).distinct().all()
    status_options = [s[0] for s in all_statuses if s[0]]
    
    # Add common statuses if not present
    common_statuses = ['Booking Created', 'Picked Up', 'In Transit', 'Arrived at Hub', 
                       'Customs Clearance', 'Out for Delivery', 'Delivered', 
                       'Delivery Attempted', 'On Hold', 'Cancelled']
    for status in common_statuses:
        if status not in status_options:
            status_options.append(status)
    
    # Get statistics
    stats = {
        'total': Shipment.query.count(),
        'active': Shipment.query.filter(~Shipment.status.in_(['Delivered', 'Cancelled'])).count(),
        'delivered': Shipment.query.filter_by(status='Delivered').count(),
        'pending_payment': Shipment.query.filter_by(status='Pending Payment').count()
    }
    
    return render_template('admin/bulk_update_shipments.html',
                         shipments=shipments,
                         status_options=sorted(status_options),
                         status_filter=status_filter,
                         date_from=date_from,
                         date_to=date_to,
                         search=search,
                         stats=stats)


def preview_bulk_email():
    """Preview email for bulk update before sending."""
    shipment_ids = request.form.getlist('shipment_ids')
    new_status = request.form.get('new_status', 'In Transit')
    location = request.form.get('location', '').strip()
    description = request.form.get('description', '').strip()
    include_image = request.form.get('include_image') == 'on'
    image_url = request.form.get('image_url', '').strip()
    
    if not shipment_ids:
        return jsonify({'error': 'No shipments selected'}), 400
    
    # Get first shipment as sample
    sample_shipment = Shipment.query.options(
        joinedload(Shipment.customer)
    ).get(shipment_ids[0])
    
    if not sample_shipment or not sample_shipment.customer:
        return jsonify({'error': 'Sample shipment has no customer'}), 400
    
    customer = sample_shipment.customer
    
    # Build preview
    base_url = os.environ.get('APP_BASE_URL', 'https://uthao.com')
    tracking_url = f"{base_url}/tracking/details/{sample_shipment.tracking_number}"
    
    status_config = {
        'Delivered': {'color': '#22c55e', 'emoji': '✅'},
        'Out for Delivery': {'color': '#8b5cf6', 'emoji': '🚚'},
        'In Transit': {'color': '#f97316', 'emoji': '📦'},
        'Picked Up': {'color': '#3b82f6', 'emoji': '📋'},
        'Arrived at Hub': {'color': '#d97706', 'emoji': '🏭'},
        'Customs Clearance': {'color': '#f59e0b', 'emoji': '🛃'},
        'On Hold': {'color': '#6b7280', 'emoji': '⏸️'},
        'Cancelled': {'color': '#ef4444', 'emoji': '❌'},
    }
    config = status_config.get(new_status, {'color': '#f97316', 'emoji': '📦'})
    
    # Build HTML preview
    image_html = f'<img src="{image_url}" style="max-width:100%;border-radius:8px;margin:16px 0;">' if include_image and image_url else ''
    
    html_preview = f"""
    <div style="max-width:600px;margin:0 auto;background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 4px 12px rgba(0,0,0,0.1);">
        <div style="background:{config['color']};padding:24px;text-align:center;color:#fff;">
            <h2 style="margin:0;">Shipment Update</h2>
            <p style="margin:8px 0 0;">Status: {new_status}</p>
        </div>
        <div style="padding:24px;">
            <p>Hi <strong>{customer.full_name or 'there'}</strong>,</p>
            <p>Your shipment <strong>#{sample_shipment.tracking_number}</strong> has been updated.</p>
            <div style="background:#f9fafb;border:2px solid {config['color']};border-radius:8px;padding:16px;margin:16px 0;">
                <p style="margin:0 0 8px;font-size:12px;color:#666;text-transform:uppercase;">New Status</p>
                <span style="display:inline-block;background:{config['color']};color:#fff;padding:6px 16px;border-radius:20px;font-weight:bold;">
                    {new_status}
                </span>
                {f"<p style='margin:12px 0 0;color:#666;'>📍 {location}</p>" if location else ""}
                {f"<p style='margin:8px 0 0;color:#666;font-style:italic;'>💬 {description}</p>" if description else ""}
            </div>
            {image_html}
            <p style="text-align:center;margin-top:24px;">
                <a href="{tracking_url}" style="display:inline-block;background:{config['color']};color:#fff;padding:12px 24px;border-radius:6px;text-decoration:none;font-weight:bold;">
                    Track Shipment
                </a>
            </p>
        </div>
    </div>
    """
    
    return jsonify({
        'success': True,
        'preview_html': html_preview,
        'recipient_count': len(shipment_ids),
        'sample_tracking': sample_shipment.tracking_number
    })


def process_bulk_update():
    """Process the actual bulk update."""
    shipment_ids = request.form.getlist('shipment_ids')
    new_status = request.form.get('new_status')
    location = request.form.get('location', '').strip()
    description = request.form.get('description', '').strip()
    notify_customers = request.form.get('notify_customers') == 'on'
    include_image = request.form.get('include_image') == 'on'
    image_url = request.form.get('image_url', '').strip()
    
    if not shipment_ids:
        flash('Please select at least one shipment.', 'error')
        return redirect(url_for('admin.bulk_update_shipments'))
    
    if not new_status:
        flash('Please select a new status.', 'error')
        return redirect(url_for('admin.bulk_update_shipments'))
    
    # Process updates
    updated_count = 0
    email_sent_count = 0
    email_failed_count = 0
    failed_shipments = []
    
    # Get all shipments with related data
    shipments = Shipment.query.options(
        joinedload(Shipment.customer),
        joinedload(Shipment.packages).joinedload(Package.images)
    ).filter(Shipment.id.in_(shipment_ids)).all()
    
    for shipment in shipments:
        try:
            old_status = shipment.status
            
            # Skip if status hasn't changed
            if old_status == new_status:
                continue
            
            # Update status
            shipment.status = new_status
            
            # Add tracking event
            event = ShipmentEvent(
                shipment_id=shipment.id,
                status=new_status,
                location=location,
                description=description or f'Bulk update to {new_status}',
                timestamp=datetime.utcnow()
            )
            db.session.add(event)
            
            # Create in-app notification
            notification = Notification(
                user_id=shipment.user_id,
                title=f'Shipment {new_status}',
                message=f'Your shipment {shipment.tracking_number} is now {new_status}.',
                notification_type=f'shipment_{new_status.lower().replace(" ", "_")}',
                related_shipment_id=shipment.id,
                link=f'/tracking?q={shipment.tracking_number}',
                priority='high' if new_status == 'Delivered' else 'normal'
            )
            db.session.add(notification)
            
            db.session.commit()
            updated_count += 1
            
            # Send email if requested
            if notify_customers and shipment.customer and shipment.customer.email:
                try:
                    # Find image if needed
                    email_image_url = None
                    email_image_cid = None
                    
                    if include_image:
                        if image_url:
                            # Use uploaded image
                            email_image_url = image_url
                            email_image_cid = 'bulk-image'
                        elif shipment.packages:
                            # Use first package image
                            for pkg in shipment.packages:
                                if pkg.images:
                                    email_image_url = pkg.images[0].image_url
                                    email_image_cid = f'pkg-img-{pkg.images[0].id}'
                                    break
                    
                    _send_status_email_smtp(
                        shipment=shipment,
                        customer=shipment.customer,
                        new_status=new_status,
                        location=location,
                        description=description,
                        image_url=email_image_url,
                        image_cid=email_image_cid
                    )
                    
                    # Log success
                    log_email(
                        user_id=shipment.user_id,
                        shipment_id=shipment.id,
                        email_type='bulk_status_update',
                        subject=f'Shipment {shipment.tracking_number} — {new_status}',
                        recipient_email=shipment.customer.email,
                        status='sent',
                        status_sent=new_status,
                        included_image=bool(email_image_url)
                    )
                    
                    email_sent_count += 1
                    
                except Exception as e:
                    current_app.logger.error(f'Email failed for {shipment.tracking_number}: {e}')
                    email_failed_count += 1
                    
                    log_email(
                        user_id=shipment.user_id,
                        shipment_id=shipment.id,
                        email_type='bulk_status_update',
                        subject=f'Shipment {shipment.tracking_number} — {new_status}',
                        recipient_email=shipment.customer.email,
                        status='failed',
                        status_sent=new_status,
                        error_message=str(e)
                    )
            
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f'Bulk update failed for shipment {shipment.id}: {e}')
            failed_shipments.append({
                'id': shipment.id,
                'tracking': shipment.tracking_number,
                'error': str(e)
            })
    
    # Build result message
    messages = [f'Updated {updated_count} shipments.']
    
    if notify_customers:
        messages.append(f'Emails sent: {email_sent_count}')
        if email_failed_count > 0:
            messages.append(f'Failed emails: {email_failed_count}')
    
    if failed_shipments:
        messages.append(f'Failed updates: {len(failed_shipments)}')
    
    flash(' '.join(messages), 
          'success' if not failed_shipments and email_failed_count == 0 else 'warning')
    
    # Store results in session for detailed view
    session['bulk_update_results'] = {
        'updated': updated_count,
        'emails_sent': email_sent_count,
        'emails_failed': email_failed_count,
        'failed': failed_shipments,
        'new_status': new_status
    }
    
    return redirect(url_for('admin.bulk_update_results'))


def process_bulk_delete():
    """Process bulk deletion of shipments."""
    shipment_ids = request.form.getlist('shipment_ids')
    confirm_text = request.form.get('confirm_text', '').strip()
    
    if not shipment_ids:
        flash('Please select shipments to delete.', 'error')
        return redirect(url_for('admin.bulk_update_shipments'))
    
    # Require confirmation
    if confirm_text != 'DELETE':
        flash('Please type DELETE to confirm bulk deletion.', 'error')
        return redirect(url_for('admin.bulk_update_shipments'))
    
    deleted_count = 0
    failed_deletions = []
    
    for shipment_id in shipment_ids:
        try:
            shipment = Shipment.query.get(shipment_id)
            if not shipment:
                continue
            
            tracking = shipment.tracking_number
            
            # Delete related records
            from app.models import ShipmentPayment, Notification, PackageImage, Package
            
            for package in shipment.packages:
                PackageImage.query.filter_by(package_id=package.id).delete()
            
            Package.query.filter_by(shipment_id=shipment_id).delete()
            ShipmentPayment.query.filter_by(shipment_id=shipment_id).delete()
            Notification.query.filter_by(related_shipment_id=shipment_id).delete()
            ShipmentEvent.query.filter_by(shipment_id=shipment_id).delete()
            
            db.session.delete(shipment)
            db.session.commit()
            
            deleted_count += 1
            current_app.logger.info(f'Bulk deleted shipment: {tracking}')
            
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f'Failed to delete shipment {shipment_id}: {e}')
            failed_deletions.append({'id': shipment_id, 'error': str(e)})
    
    flash(f'Deleted {deleted_count} shipments.' + 
          (f' Failed: {len(failed_deletions)}' if failed_deletions else ''),
          'success' if not failed_deletions else 'warning')
    
    return redirect(url_for('admin.bulk_update_shipments'))


@admin_bp.route('/shipments/bulk-update/results')
@login_required
@admin_required
def bulk_update_results():
    """Show detailed results of bulk update operation."""
    results = session.get('bulk_update_results', {})
    
    if not results:
        flash('No recent bulk update found.', 'error')
        return redirect(url_for('admin.bulk_update_shipments'))
    
    # Clear from session after displaying
    session.pop('bulk_update_results', None)
    
    return render_template('admin/bulk_update_results.html', results=results)


def _send_status_email_smtp(shipment, customer, new_status, location, description, 
                            image_url=None, image_cid=None):
    """Send shipment status update email via SMTP with optional image."""
    
    # Get URLs from environment
    base_url = os.environ.get('APP_BASE_URL', 'https://uthao.com')
    tracking_path = os.environ.get('TRACKING_URL_PATH', '/tracking/details/')
    tracking_url = f"{base_url.rstrip('/')}{tracking_path}{shipment.tracking_number}"
    
    # Status colors and emojis
    status_config = {
        'Delivered': {'color': '#22c55e', 'emoji': '✅'},
        'Out for Delivery': {'color': '#8b5cf6', 'emoji': '🚚'},
        'In Transit': {'color': '#f97316', 'emoji': '📦'},
        'Picked Up': {'color': '#3b82f6', 'emoji': '📋'},
        'Arrived at Hub': {'color': '#d97706', 'emoji': '🏭'},
        'Customs Clearance': {'color': '#f59e0b', 'emoji': '🛃'},
        'On Hold': {'color': '#6b7280', 'emoji': '⏸️'},
        'Cancelled': {'color': '#ef4444', 'emoji': '❌'},
    }
    config = status_config.get(new_status, {'color': '#f97316', 'emoji': '📦'})
    color = config['color']
    emoji = config['emoji']

    # Build location and ETA strings
    location_html = f"<p style='margin:12px 0 0;color:#6b7280;font-size:14px;'>📍 <strong>Location:</strong> {location}</p>" if location else ""
    eta_html = f"<p style='margin:8px 0 0;color:#6b7280;font-size:14px;'>📅 <strong>Est. Delivery:</strong> {shipment.estimated_delivery.strftime('%d %b %Y')}</p>" if shipment.estimated_delivery else ""
    desc_html = f"<p style='margin:12px 0 0;color:#6b7280;font-size:14px;font-style:italic;'>💬 {description}</p>" if description else ""

    # Image HTML if included
    image_html = ""
    if image_url and image_cid:
        image_html = f"""
        <tr>
            <td style="padding:0 24px 20px;">
                <p style="margin:0 0 10px;font-size:13px;color:#6b7280;">📷 Package Photo:</p>
                <img src="cid:{image_cid}" alt="Package" style="max-width:100%;height:auto;border-radius:8px;border:1px solid #e5e7eb;max-height:400px;object-fit:cover;">
            </td>
        </tr>
        """

    # PLAIN TEXT version
    text_body = f"""{emoji} Shipment Update - {new_status}

        Hi {customer.full_name or 'there'},

        Your shipment {shipment.tracking_number} has been updated.

        ━━━━━━━━━━━━━━━━━━━━━━━━━━━
        NEW STATUS: {new_status}
        ━━━━━━━━━━━━━━━━━━━━━━━━━━━

        {f"📍 Location: {location}" if location else ""}
        {f"📅 Est. Delivery: {shipment.estimated_delivery.strftime('%d %b %Y')}" if shipment.estimated_delivery else ""}
        From: {shipment.origin}
        To: {shipment.destination}

        {f"Note: {description}" if description else ""}

        {f"📷 Package photo included in this email." if image_url else ""}

        Track your shipment:
        {tracking_url}

        Need help? Contact support@uthao.com

        ---
        UTHAO Logistics
        {base_url}
    """

    # HTML version
    html_body = f"""<!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Shipment Update - {shipment.tracking_number}</title>
        </head>
        <body style="margin:0;padding:0;background-color:#f3f4f6;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;">
            <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0">
                <tr>
                    <td align="center" style="padding:20px 10px;">
                        <table role="presentation" width="600" cellspacing="0" cellpadding="0" border="0" style="background:#ffffff;border-radius:12px;overflow:hidden;max-width:600px;width:100%;">
                            
                            <!-- Header -->
                            <tr>
                                <td style="background:{color};padding:32px 24px;text-align:center;">
                                    <h1 style="margin:0;color:#ffffff;font-size:24px;font-weight:800;letter-spacing:-0.5px;">{emoji} Shipment Update</h1>
                                    <p style="margin:8px 0 0;color:rgba(255,255,255,0.9);font-size:14px;">Your shipment status has changed</p>
                                </td>
                            </tr>
                            
                            <!-- Body -->
                            <tr>
                                <td style="padding:28px 24px 20px;">
                                    <p style="margin:0 0 20px;color:#374151;font-size:16px;line-height:1.6;">
                                        Hi <strong>{customer.full_name or 'there'}</strong>,
                                    </p>
                                    
                                    <p style="margin:0 0 24px;color:#374151;font-size:15px;line-height:1.6;">
                                        Your shipment <strong style="font-family:monospace;background:#f3f4f6;padding:3px 10px;border-radius:6px;font-size:14px;">{shipment.tracking_number}</strong> has been updated to:
                                    </p>
                                </td>
                            </tr>

                            <!-- Status Box -->
                            <tr>
                                <td style="padding:0 24px 20px;">
                                    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background:#f9fafb;border:2px solid {color};border-radius:12px;">
                                        <tr>
                                            <td style="padding:20px;">
                                                <p style="margin:0 0 8px;font-size:11px;font-weight:700;color:#9ca3af;text-transform:uppercase;letter-spacing:0.08em;">Current Status</p>
                                                <table role="presentation" cellspacing="0" cellpadding="0" border="0">
                                                    <tr>
                                                        <td style="background:{color};color:#ffffff;padding:8px 20px;border-radius:20px;font-size:16px;font-weight:700;">
                                                            {new_status}
                                                        </td>
                                                    </tr>
                                                </table>
                                                {f"<p style='margin:12px 0 0;color:#6b7280;font-size:14px;'>📍 <strong>Location:</strong> {location}</p>" if location else ""}
                                                {f"<p style='margin:8px 0 0;color:#6b7280;font-size:14px;'>📅 <strong>Est. Delivery:</strong> {shipment.estimated_delivery.strftime('%d %b %Y')}</p>" if shipment.estimated_delivery else ""}
                                                {f"<p style='margin:12px 0 0;color:#6b7280;font-size:14px;font-style:italic;'>💬 {description}</p>" if description else ""}
                                            </td>
                                        </tr>
                                    </table>
                                </td>
                            </tr>

                            <!-- Package Image (if included) -->
                            {image_html}

                            <!-- Route -->
                            <tr>
                                <td style="padding:0 24px 24px;">
                                    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background:#fff7ed;border:1px solid #ffedd5;border-radius:10px;">
                                        <tr>
                                            <td style="padding:16px 20px;">
                                                <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0">
                                                    <tr>
                                                        <td style="width:40%;">
                                                            <p style="margin:0;font-size:11px;color:#9ca3af;font-weight:700;text-transform:uppercase;letter-spacing:0.05em;">From</p>
                                                            <p style="margin:4px 0 0;font-size:14px;font-weight:600;color:#111827;line-height:1.4;">{shipment.origin}</p>
                                                        </td>
                                                        <td style="width:20%;text-align:center;vertical-align:middle;">
                                                            <div style="color:#f97316;font-size:24px;">→</div>
                                                        </td>
                                                        <td style="width:40%;text-align:right;">
                                                            <p style="margin:0;font-size:11px;color:#9ca3af;font-weight:700;text-transform:uppercase;letter-spacing:0.05em;">To</p>
                                                            <p style="margin:4px 0 0;font-size:14px;font-weight:600;color:#111827;line-height:1.4;">{shipment.destination}</p>
                                                        </td>
                                                    </tr>
                                                </table>
                                            </td>
                                        </tr>
                                    </table>
                                </td>
                            </tr>

                            <!-- CTA Button -->
                            <tr>
                                <td style="padding:0 24px 28px;text-align:center;">
                                    <table role="presentation" cellspacing="0" cellpadding="0" border="0" style="margin:0 auto;">
                                        <tr>
                                            <td style="background:{color};border-radius:8px;text-align:center;mso-padding-alt:12px 28px;">
                                                <a href="{tracking_url}" 
                                                style="display:inline-block;padding:14px 32px;color:#ffffff;font-size:15px;font-weight:700;text-decoration:none;border-radius:8px;">
                                                    Track Your Shipment
                                                </a>
                                            </td>
                                        </tr>
                                    </table>
                                    <p style="margin:12px 0 0;font-size:12px;color:#9ca3af;">
                                        Or visit: <a href="{tracking_url}" style="color:#6b7280;text-decoration:underline;">{tracking_url}</a>
                                    </p>
                                </td>
                            </tr>

                            <!-- Footer -->
                            <tr>
                                <td style="padding:24px;border-top:1px solid #f3f4f6;background:#f9fafb;text-align:center;">
                                    <p style="margin:0 0 8px;color:#9ca3af;font-size:13px;">
                                        Need help? Contact <a href="mailto:support@uthao.com" style="color:#f97316;text-decoration:none;">support@uthao.com</a>
                                    </p>
                                    <p style="margin:0;color:#9ca3af;font-size:12px;">
                                        © {datetime.utcnow().year} UTHAO Logistics · <a href="{base_url}" style="color:#9ca3af;text-decoration:underline;">{base_url.replace('https://', '')}</a>
                                    </p>
                                </td>
                            </tr>
                        </table>
                    </td>
                </tr>
            </table>
        </body>
        </html>"""

    # Send via SMTP
    send_smtp_email(
        to_email=customer.email,
        to_name=customer.full_name,
        subject=f'{emoji} Shipment {shipment.tracking_number} — {new_status}',
        html_body=html_body,
        text_body=text_body,
        image_url=image_url,
        image_cid=image_cid
    )



def _send_status_email(shipment, new_status, location, description):
    """Send shipment status update email via Mailjet."""
    import os
    from mailjet_rest import Client

    api_key    = os.environ.get('MAILJET_API_KEY')
    api_secret = os.environ.get('MAILJET_API_SECRET')

    print(f'--- Mailjet email attempt ---')
    print(f'API key set: {bool(api_key)}')
    print(f'API secret set: {bool(api_secret)}')
    print(f'Sending to: {shipment.customer.email}')
    print(f'From: {os.environ.get("MAIL_DEFAULT_SENDER")}')

    if not api_key or not api_secret:
        print('Mailjet credentials not set — skipping email.')
        return

    # Status colour for the email banner
    status_colors = {
        'Delivered':          '#22c55e',
        'Out for Delivery':   '#8b5cf6',
        'In Transit':         '#f97316',
        'Picked Up':          '#3b82f6',
        'Customs Clearance':  '#f59e0b',
        'On Hold':            '#6b7280',
        'Cancelled':          '#ef4444',
    }
    color = status_colors.get(new_status, '#f97316')

    eta_line = ''
    if shipment.estimated_delivery:
        eta_line = f"<p style='margin:8px 0;color:#6b7280;font-size:14px;'>📅 Estimated Delivery: <strong>{shipment.estimated_delivery.strftime('%d %b %Y')}</strong></p>"

    location_line = ''
    if location:
        location_line = f"<p style='margin:8px 0;color:#6b7280;font-size:14px;'>📍 Current Location: <strong>{location}</strong></p>"

    html_body = f"""
    <div style="font-family:-apple-system,BlinkMacSystemFont,'Helvetica Neue',Arial,sans-serif;max-width:560px;margin:0 auto;background:#ffffff;">
      
      <!-- Header -->
      <div style="background:{color};padding:32px 24px;text-align:center;border-radius:12px 12px 0 0;">
        <h1 style="margin:0;color:#ffffff;font-size:22px;font-weight:800;letter-spacing:-0.5px;">
          Shipment Update
        </h1>
        <p style="margin:8px 0 0;color:rgba(255,255,255,0.85);font-size:14px;">
          Your shipment status has changed
        </p>
      </div>

      <!-- Body -->
      <div style="padding:28px 24px;border:1px solid #e5e7eb;border-top:none;border-radius:0 0 12px 12px;">
        
        <p style="margin:0 0 20px;color:#374151;font-size:15px;">
          Hi <strong>{shipment.customer.full_name or 'there'}</strong>,
        </p>

        <p style="margin:0 0 20px;color:#374151;font-size:15px;">
          Your shipment <strong style="font-family:monospace;background:#f3f4f6;padding:2px 8px;border-radius:4px;">{shipment.tracking_number}</strong> has been updated.
        </p>

        <!-- Status badge -->
        <div style="background:#f9fafb;border:1px solid #e5e7eb;border-radius:10px;padding:16px 20px;margin-bottom:20px;">
          <p style="margin:0 0 8px;font-size:12px;font-weight:600;color:#9ca3af;text-transform:uppercase;letter-spacing:0.05em;">New Status</p>
          <div style="display:inline-block;background:{color};color:#ffffff;padding:6px 16px;border-radius:20px;font-size:14px;font-weight:700;">
            {new_status}
          </div>
          {location_line}
          {eta_line}
          {f"<p style='margin:8px 0 0;color:#6b7280;font-size:14px;'>💬 {description}</p>" if description else ''}
        </div>

        <!-- Route -->
        <div style="display:flex;justify-content:space-between;background:#fff7ed;border:1px solid #ffedd5;border-radius:10px;padding:14px 20px;margin-bottom:24px;">
          <div>
            <div style="font-size:11px;color:#9ca3af;font-weight:600;text-transform:uppercase;margin-bottom:2px;">From</div>
            <div style="font-size:14px;font-weight:700;color:#111827;">{shipment.origin}</div>
          </div>
          <div style="color:#f97316;font-size:18px;align-self:center;">→</div>
          <div style="text-align:right;">
            <div style="font-size:11px;color:#9ca3af;font-weight:600;text-transform:uppercase;margin-bottom:2px;">To</div>
            <div style="font-size:14px;font-weight:700;color:#111827;">{shipment.destination}</div>
          </div>
        </div>

        <p style="margin:0 0 24px;color:#6b7280;font-size:13px;line-height:1.6;">
          You can track your shipment in real time using the button below.
        </p>

        <!-- CTA -->
        <div style="text-align:center;margin-bottom:24px;">
          <a href="https://uthao.com/tracking/details/{shipment.tracking_number}"
             style="display:inline-block;background:{color};color:#ffffff;padding:12px 28px;border-radius:8px;font-size:15px;font-weight:700;text-decoration:none;">
            Track Shipment
          </a>
        </div>

        <hr style="border:none;border-top:1px solid #f3f4f6;margin:20px 0;">
        <p style="margin:0;color:#9ca3af;font-size:12px;text-align:center;">
          UTHAO Logistics · If you have questions, contact our support team.
        </p>
      </div>
    </div>
    """

    mailjet = Client(auth=(api_key, api_secret), version='v3.1')

    data = {
        'Messages': [{
            'From': {
                'Email': os.environ.get('MAIL_DEFAULT_SENDER', 'noreply@uthao.com'),
                'Name':  'UTHAO Logistics'
            },
            'To': [{
                'Email': shipment.customer.email,
                'Name':  shipment.customer.full_name or shipment.customer.email
            }],
            'Subject': f'Shipment {shipment.tracking_number} — {new_status}',
            'HTMLPart': html_body,
        }]
    }

    try:
        result = mailjet.send.create(data=data)
        if result.status_code == 200:
            current_app.logger.info(f'Status email sent to {shipment.customer.email}')
        else:
            current_app.logger.error(f'Mailjet error {result.status_code}: {result.json()}')
    except Exception as e:
        current_app.logger.error(f'Mailjet exception: {e}')


@admin_bp.route('/bulk-email', methods=['GET', 'POST'])
@login_required
@admin_required
def bulk_email():
    """Send bulk emails to multiple users with Cloudinary image upload."""

    if request.method == 'POST':
        # Check if this is an AJAX image upload request
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        has_image_only = request.files.get('image_file') and not request.form.get('subject')
        
        # Handle AJAX image upload separately
        if is_ajax or (request.files.get('image_file') and has_image_only):
            return handle_image_upload()
        
        # Regular form submission - send emails
        user_ids = request.form.getlist('user_ids')
        subject = request.form.get('subject', '').strip()
        message = request.form.get('message', '').strip()
        email_type = request.form.get('email_type', 'general')
        image_url = request.form.get('uploaded_image_url', '').strip()
        
        if not user_ids:
            flash('Please select at least one user.', 'error')
            return redirect(url_for('admin.bulk_email'))
        
        if not subject or not message:
            flash('Subject and message are required.', 'error')
            return redirect(url_for('admin.bulk_email'))


        users = User.query.filter(User.id.in_(user_ids)).all()
        sent_count = 0
        failed_count = 0
        
        for user in users:
            if not user.email:
                continue
                
            try:
                html_body = build_bulk_email_html(user, subject, message, image_url)
                text_body = f"Hi {user.full_name or 'there'},\n\n{message}\n\n---\nUTHAO Logistics"
                
                send_smtp_email(
                    to_email=user.email,
                    to_name=user.full_name,
                    subject=subject,
                    html_body=html_body,
                    text_body=text_body,
                    image_url=image_url if image_url else None,
                    image_cid='bulk-email-image' if image_url else None
                )
                
                log_email(
                    user_id=user.id,
                    shipment_id=None,
                    email_type=email_type,
                    subject=subject,
                    recipient_email=user.email,
                    status='sent',
                    included_image=bool(image_url)
                )
                
                sent_count += 1
                
            except Exception as e:
                current_app.logger.error(f'Bulk email failed for {user.email}: {e}')
                log_email(
                    user_id=user.id,
                    shipment_id=None,
                    email_type=email_type,
                    subject=subject,
                    recipient_email=user.email,
                    status='failed',
                    error_message=str(e)
                )
                failed_count += 1
        
        flash(f'Emails sent: {sent_count}, Failed: {failed_count}', 
              'success' if failed_count == 0 else 'warning')
        return redirect(url_for('admin.bulk_email'))
    
    # GET request
    page = request.args.get('page', 1, type=int)
    search = request.args.get('q', '').strip()
    plan_filter = request.args.get('plan', '').strip()
    
    query = User.query.filter_by(is_active=True)
    
    if search:
        query = query.filter(
            db.or_(
                User.email.ilike(f'%{search}%'),
                User.full_name.ilike(f'%{search}%')
            )
        )
    
    if plan_filter:
        query = query.join(Subscription).filter(Subscription.plan_id == plan_filter)
    
    users = query.order_by(User.id.desc()).paginate(
        page=page, per_page=50, error_out=False
    )
    
    return render_template('admin/bulk_email.html', 
                         users=users, 
                         plans=PLANS,
                         search=search,
                         plan_filter=plan_filter,
                         cloudinary_cloud=os.environ.get('CLOUDINARY_CLOUD_NAME'),
                         cloudinary_preset=os.environ.get('CLOUDINARY_UPLOAD_PRESET', 'bulk_emails'))



@admin_bp.route('/bulk-email/upload-image', methods=['POST'])
@login_required
@admin_required
def upload_bulk_email_image():
    """Dedicated endpoint for image uploads."""
    return handle_image_upload()


def handle_image_upload():
    """Handle Cloudinary image upload via AJAX."""
    try:
        if 'image_file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        
        file = request.files['image_file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        # Upload to Cloudinary
        import cloudinary.uploader
        
        upload_result = cloudinary.uploader.upload(
            file,
            folder='bulk_emails',
            resource_type='auto',
            transformation=[
                {'width': 800, 'crop': 'limit'},
                {'quality': 'auto:good'}
            ]
        )
        
        return jsonify({
            'success': True,
            'url': upload_result['secure_url'],
            'public_id': upload_result['public_id'],
            'thumbnail': cloudinary.CloudinaryImage(upload_result['public_id']).build_url(
                width=200, crop='fill'
            )
        })
        
    except Exception as e:
        current_app.logger.error(f'Image upload failed: {e}')
        return jsonify({'error': str(e)}), 500


def build_bulk_email_html(user, subject, message, image_url=None):
    """Build HTML email template."""
    message_html = message.replace('\n', '<br>')
    
    image_section = f'''
    <tr>
        <td style="padding:0 24px 24px;">
            <img src="{image_url}" alt="Email Image" 
                 style="max-width:100%;height:auto;border-radius:8px;border:1px solid #e5e7eb;">
        </td>
    </tr>
    ''' if image_url else ''
    
    return f"""<!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{subject}</title>
    </head>
    <body style="margin:0;padding:0;background-color:#f3f4f6;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;">
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0">
            <tr>
                <td align="center" style="padding:20px 10px;">
                    <table role="presentation" width="600" cellspacing="0" cellpadding="0" border="0" style="background:#ffffff;border-radius:12px;overflow:hidden;max-width:600px;width:100%;box-shadow:0 4px 6px rgba(0,0,0,0.1);">
                        <tr>
                            <td style="background:linear-gradient(135deg, #f97316 0%, #ea580c 100%);padding:32px 24px;text-align:center;">
                                <h1 style="margin:0;color:#ffffff;font-size:24px;font-weight:800;">UTHAO Logistics</h1>
                            </td>
                        </tr>
                        <tr>
                            <td style="padding:28px 24px 20px;">
                                <p style="margin:0 0 20px;color:#374151;font-size:16px;line-height:1.6;">
                                    Hi <strong>{user.full_name or 'there'}</strong>,
                                </p>
                                <div style="color:#374151;font-size:15px;line-height:1.6;">
                                    {message_html}
                                </div>
                            </td>
                        </tr>
                        {image_section}
                        <tr>
                            <td style="padding:24px;border-top:1px solid #f3f4f6;background:#f9fafb;text-align:center;">
                                <p style="margin:0 0 8px;color:#9ca3af;font-size:13px;">
                                    Need help? Contact <a href="mailto:support@uthao.com" style="color:#f97316;text-decoration:none;">support@uthao.com</a>
                                </p>
                                <p style="margin:0;color:#9ca3af;font-size:12px;">
                                    © {datetime.utcnow().year} UTHAO Logistics
                                </p>
                            </td>
                        </tr>
                    </table>
                </td>
            </tr>
        </table>
    </body>
    </html>"""


# Hi there! Thanks for choosing UTHAO. We're excited to help with your shipping needs. Track your packages easily at our website. Questions? Reply to this email.


@admin_bp.route('/email-analytics')
@login_required
@admin_required
def email_analytics():
    """View email sending statistics."""
    
    from datetime import datetime, timedelta
    
    # Date range
    days = request.args.get('days', 30, type=int)
    since = datetime.utcnow() - timedelta(days=days)
    
    # Stats
    total_sent = EmailLog.query.filter(EmailLog.created_at >= since).count()
    successful = EmailLog.query.filter(
        EmailLog.created_at >= since,
        EmailLog.status == 'sent'
    ).count()
    failed = EmailLog.query.filter(
        EmailLog.created_at >= since,
        EmailLog.status == 'failed'
    ).count()
    
    # By type
    by_type = db.session.query(
        EmailLog.email_type,
        db.func.count(EmailLog.id)
    ).filter(EmailLog.created_at >= since).group_by(EmailLog.email_type).all()
    
    # Recent emails
    recent_emails = EmailLog.query.order_by(
        EmailLog.created_at.desc()
    ).limit(50).all()
    
    # Top recipients (for monitoring)
    top_recipients = db.session.query(
        EmailLog.recipient_email,
        db.func.count(EmailLog.id)
    ).filter(EmailLog.created_at >= since).group_by(
        EmailLog.recipient_email
    ).order_by(db.func.count(EmailLog.id).desc()).limit(10).all()
    
    return render_template('admin/email_analytics.html',
                         stats={
                             'total': total_sent,
                             'successful': successful,
                             'failed': failed,
                             'success_rate': (successful / total_sent * 100) if total_sent > 0 else 0
                         },
                         by_type=dict(by_type),
                         recent_emails=recent_emails,
                         top_recipients=top_recipients,
                         days=days)



@admin_bp.route('/shipments/<int:shipment_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_shipment(shipment_id):
    shipment = Shipment.query.get_or_404(shipment_id)
    tracking = shipment.tracking_number


    # Delete package images first (deepest level)
    for package in shipment.packages:
        PackageImage.query.filter_by(package_id=package.id).delete()

    # Delete everything else linked to shipment
    Package.query.filter_by(shipment_id=shipment_id).delete()
    ShipmentPayment.query.filter_by(shipment_id=shipment_id).delete()
    Notification.query.filter_by(related_shipment_id=shipment_id).delete()

    db.session.delete(shipment)
    db.session.commit()

    flash(f'Shipment {tracking} has been permanently deleted.', 'success')
    return redirect(url_for('admin.shipments'))
# ────────────────────────────────────────────
# Payment Management
# ────────────────────────────────────────────

# @admin_bp.route('/payments')
# @login_required
# @admin_required
# def payments():
#     """View all payment requests."""
#     page = request.args.get('page', 1, type=int)
#     status = request.args.get('status', 'pending').strip()
    
#     query = PaymentRequest.query
    
#     if status != 'all':
#         query = query.filter_by(status=status)
    
#     payments = query.order_by(PaymentRequest.created_at.desc()).paginate(
#         page=page, per_page=20, error_out=False
#     )
    
#     return render_template(
#         'admin/payments.html',
#         payments=payments,
#         status=status
#     )

@admin_bp.route('/payments/<int:payment_id>')
@login_required
@admin_required
def payment_detail(payment_id):
    payment = PaymentRequest.query.get_or_404(payment_id)
    return render_template('admin/payment_detail.html', payment=payment)


@admin_bp.route('/payments/<int:payment_id>/approve', methods=['POST'])
@login_required
@admin_required
def approve_payment(payment_id):
    """Approve payment and upgrade user plan."""
    payment = PaymentRequest.query.get_or_404(payment_id)
    
    if payment.status != 'pending':
        flash('This payment has already been processed.', 'error')
        return redirect(url_for('admin.payments'))
    
    notes = request.form.get('notes', '').strip()
    
    try:
        payment.approve(current_user.id, notes)
        
        # Notify user
        notification = Notification(
            user_id=payment.user_id,
            title='Payment Approved',
            message=f'Your payment for {payment.requested_plan_name} has been approved.',
            notification_type='payment_success',
            link='/settings?tab=billing',
            priority='high'
        )
        db.session.add(notification)
        db.session.commit()
        
        flash(f'Payment approved. User upgraded to {payment.requested_plan_name}.', 'success')
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Payment approval error: {e}")
        flash('Error processing approval.', 'error')
    
    return redirect(url_for('admin.payments'))

@admin_bp.route('/payments/<int:payment_id>/reject', methods=['POST'])
@login_required
@admin_required
def reject_payment(payment_id):
    """Reject payment request."""
    payment = PaymentRequest.query.get_or_404(payment_id)
    
    if payment.status != 'pending':
        flash('This payment has already been processed.', 'error')
        return redirect(url_for('admin.payments'))
    
    notes = request.form.get('notes', '').strip()
    
    if not notes:
        flash('Please provide a reason for rejection.', 'error')
        return redirect(url_for('admin.payment_detail', payment_id=payment.id))
    
    payment.reject(current_user.id, notes)
    
    # Notify user
    notification = Notification(
        user_id=payment.user_id,
        title='Payment Declined',
        message=f'Your payment was declined. Reason: {notes}',
        notification_type='payment_failed',
        link='/support',
        priority='high'
    )
    db.session.add(notification)
    db.session.commit()
    
    flash('Payment request rejected.', 'success')
    return redirect(url_for('admin.payments'))

# ────────────────────────────────────────────
# Support Tickets
# ────────────────────────────────────────────

@admin_bp.route('/tickets')
@login_required
@admin_required
def tickets():
    """View all support tickets."""
    page = request.args.get('page', 1, type=int)
    status = request.args.get('status', 'open').strip()
    
    query = SupportTicket.query
    
    if status != 'all':
        query = query.filter_by(status=status)
    
    tickets = query.order_by(
        SupportTicket.priority.desc(),
        SupportTicket.created_at.desc()
    ).paginate(page=page, per_page=20, error_out=False)
    
    return render_template(
        'admin/tickets.html',
        tickets=tickets,
        status=status
    )

@admin_bp.route('/tickets/<int:ticket_id>')
@login_required
@admin_required
def ticket_detail(ticket_id):
    """View and reply to ticket."""
    ticket = SupportTicket.query.get_or_404(ticket_id)
    return render_template('admin/ticket_detail.html', ticket=ticket)

@admin_bp.route('/tickets/<int:ticket_id>/reply', methods=['POST'])
@login_required
@admin_required
def reply_ticket(ticket_id):
    """Add staff reply to ticket."""
    ticket = SupportTicket.query.get_or_404(ticket_id)
    
    message = request.form.get('message', '').strip()
    status = request.form.get('status', 'in_progress')
    
    if not message:
        flash('Please enter a reply message.', 'error')
        return redirect(url_for('admin.ticket_detail', ticket_id=ticket.id))
    
    reply = TicketReply(
        ticket_id=ticket.id,
        user_id=current_user.id,
        message=message,
        is_staff=True
    )
    db.session.add(reply)
    
    ticket.status = status
    ticket.updated_at = datetime.utcnow()
    
    # Notify user
    notification = Notification(
        user_id=ticket.user_id,
        title='New Support Reply',
        message=f'Support responded to your ticket: {ticket.subject}',
        notification_type='ticket_reply',
        related_ticket_id=ticket.id,
        link=f'/help/ticket/{ticket.id}',
        priority='normal'
    )
    db.session.add(notification)
    db.session.commit()
    
    flash('Reply sent successfully.', 'success')
    return redirect(url_for('admin.ticket_detail', ticket_id=ticket.id))


# ────────────────────────────────────────────
# Settings & Configuration
# ────────────────────────────────────────────

@admin_bp.route('/settings')
@login_required
@admin_required
def settings():
    """Admin settings and configuration."""
    payment_methods = PaymentMethod.query.order_by(PaymentMethod.sort_order).all()
    return render_template('admin/settings.html', payment_methods=payment_methods)


@admin_bp.route('/payment-methods')
@login_required
@admin_required
def payment_methods():
    """List all payment methods."""
    methods = PaymentMethod.query.order_by(PaymentMethod.sort_order, PaymentMethod.id).all()
    return render_template('admin/payment_methods.html', methods=methods)


@admin_bp.route('/payment-methods/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_payment_method():
    """Add a new payment method."""
    if request.method == 'POST':
        try:
            raw_config = request.form.get('config', '{}')
            config = json.loads(raw_config) if raw_config else {}

            # Validate unique code
            code = request.form.get('code', '').strip().lower().replace(' ', '_')
            if PaymentMethod.query.filter_by(code=code).first():
                flash(f'A payment method with code "{code}" already exists.', 'error')
                return redirect(url_for('admin.payment_methods'))

            method = PaymentMethod(
                name         = request.form.get('name', '').strip(),
                code         = code,
                display_name = request.form.get('display_name', '').strip(),
                method_type  = request.form.get('method_type', 'crypto'),
                config       = config,
                icon         = request.form.get('icon', 'fa-money-bill').strip(),
                sort_order   = int(request.form.get('sort_order', 0) or 0),
                is_active    = request.form.get('is_active') == 'on',
            )
            db.session.add(method)
            db.session.commit()
            flash(f'Payment method "{method.display_name or method.name}" added successfully.', 'success')

        except json.JSONDecodeError:
            flash('Invalid JSON in config. Please check the configuration.', 'error')
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f'Add payment method error: {e}', exc_info=True)
            flash(f'Error adding payment method: {str(e)}', 'error')

    return redirect(url_for('admin.payment_methods'))


@admin_bp.route('/payment-methods/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_payment_method(id):
    """Edit an existing payment method."""
    method = PaymentMethod.query.get_or_404(id)

    if request.method == 'POST':
        try:
            raw_config = request.form.get('config', '{}')
            config = json.loads(raw_config) if raw_config else {}

            # Check code uniqueness (excluding self)
            new_code = request.form.get('code', '').strip().lower().replace(' ', '_')
            conflict = PaymentMethod.query.filter(
                PaymentMethod.code == new_code,
                PaymentMethod.id   != id
            ).first()
            if conflict:
                flash(f'Code "{new_code}" is already used by another method.', 'error')
                return redirect(url_for('admin.payment_methods'))

            method.name         = request.form.get('name', '').strip()
            method.code         = new_code
            method.display_name = request.form.get('display_name', '').strip()
            method.method_type  = request.form.get('method_type', 'crypto')
            method.config       = config
            method.icon         = request.form.get('icon', 'fa-money-bill').strip()
            method.sort_order   = int(request.form.get('sort_order', 0) or 0)
            method.is_active    = request.form.get('is_active') == 'on'

            db.session.commit()
            flash(f'Payment method "{method.display_name or method.name}" updated.', 'success')

        except json.JSONDecodeError:
            flash('Invalid JSON in config.', 'error')
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f'Edit payment method error: {e}', exc_info=True)
            flash(f'Error updating: {str(e)}', 'error')

    return redirect(url_for('admin.payment_methods'))


@admin_bp.route('/payment-methods/<int:id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_payment_method(id):
    """Delete a payment method, blocked if pending payments exist."""
    method = PaymentMethod.query.get_or_404(id)

    pending = ShipmentPayment.query.filter_by(
        payment_method_id=id, status='pending'
    ).count() + PaymentRequest.query.filter_by(
        payment_method_id=id, status='pending'
    ).count()

    if pending > 0:
        flash(f'Cannot delete: {pending} pending payment(s) use this method.', 'error')
        return redirect(url_for('admin.payment_methods'))

    name = method.display_name or method.name
    db.session.delete(method)
    db.session.commit()
    flash(f'Payment method "{name}" deleted.', 'success')
    return redirect(url_for('admin.payment_methods'))


@admin_bp.route('/payment-methods/<int:id>/toggle', methods=['POST'])
@login_required
@admin_required
def toggle_payment_method(id):
    """Toggle a payment method active/inactive (AJAX)."""
    method = PaymentMethod.query.get_or_404(id)
    method.is_active = not method.is_active
    db.session.commit()
    return jsonify({
        'success': True,
        'is_active': method.is_active,
        'message': f'{"Activated" if method.is_active else "Deactivated"}: {method.display_name or method.name}',
    })


@admin_bp.route('/settings/payment-methods/<int:method_id>', methods=['POST'])
@login_required
@admin_required
def update_payment_method(method_id):
    """Update payment method details."""
    method = PaymentMethod.query.get_or_404(method_id)
    
    method.display_name = request.form.get('display_name', method.display_name)
    method.wallet_address = request.form.get('wallet_address', method.wallet_address)
    method.bank_name = request.form.get('bank_name', method.bank_name)
    method.account_name = request.form.get('account_name', method.account_name)
    method.account_number = request.form.get('account_number', method.account_number)
    method.paypal_email = request.form.get('paypal_email', method.paypal_email)
    method.is_active = request.form.get('is_active') == 'on'
    
    db.session.commit()
    flash(f'{method.name} updated successfully.', 'success')
    return redirect(url_for('admin.settings'))

# ────────────────────────────────────────────
# API Endpoints for AJAX
# ────────────────────────────────────────────

@admin_bp.route('/api/stats')
@login_required
@admin_required
def api_stats():
    """Get real-time stats for dashboard."""
    today = datetime.utcnow()
    thirty_days_ago = today - timedelta(days=30)
    
    return jsonify({
        'users': {
            'total': User.query.count(),
            'new_this_month': User.query.filter(User.created_at >= thirty_days_ago).count()
        },
        'shipments': {
            'total': Shipment.query.count(),
            'active': Shipment.query.filter(~Shipment.status.in_(['Delivered', 'Cancelled'])).count()
        },
        'revenue': {
            'total': float(db.session.query(func.sum(PaymentRequest.amount_usd)).filter(
                PaymentRequest.status == 'approved'
            ).scalar() or 0),
            'pending_payments': PaymentRequest.query.filter_by(status='pending').count()
        },
        'support': {
            'open_tickets': SupportTicket.query.filter_by(status='open').count()
        }
    })


@admin_bp.route('/plans')
@login_required
@admin_required
def plans():
    """List all plans with subscriber counts and revenue stats."""

    all_plans = Plan.query.order_by(Plan.sort_order.asc(), Plan.id.asc()).all()

    # Subscriber counts per plan_key
    counts_raw = db.session.query(
        Subscription.plan_id,
        func.count(Subscription.id)
    ).filter_by(status='active').group_by(Subscription.plan_id).all()
    subscriber_counts = {row[0]: row[1] for row in counts_raw}

    # Aggregate stats
    total_subscribers = sum(subscriber_counts.values())

    monthly_revenue = sum(
        (p.price_usd or 0) * subscriber_counts.get(p.plan_key, 0)
        for p in all_plans
    )

    # Free = users with no subscription OR on the free plan
    free_users = (
        User.query.filter_by(is_active=True)
        .outerjoin(Subscription)
        .filter(
            db.or_(
                Subscription.id == None,
                Subscription.plan_id == 'free'
            )
        )
        .count()
    )

    return render_template(
        'admin/plans.html',
        plans=all_plans,
        subscriber_counts=subscriber_counts,
        total_subscribers=total_subscribers,
        monthly_revenue=monthly_revenue,
        free_users=free_users,
    )


@admin_bp.route('/plans/create', methods=['POST'])
@login_required
@admin_required
def create_plan():
    """Create a new subscription plan."""

    name      = request.form.get('name', '').strip()
    plan_key  = request.form.get('plan_key', '').strip().lower()
    raw_price = request.form.get('price_usd', '').strip()
    raw_ships = request.form.get('shipments', '').strip()
    interval  = request.form.get('interval', 'month').strip()
    sort_order= request.form.get('sort_order', '0').strip()
    description = request.form.get('description', '').strip()
    is_active = request.form.get('is_active') == 'on'
    is_featured = request.form.get('is_featured') == 'on'
    features  = [f.strip() for f in request.form.getlist('features[]') if f.strip()]

    # ── Validation ────────────────────────────────────────────────
    errors = []
    if not name:
        errors.append('Plan name is required.')
    if not plan_key:
        errors.append('Plan key is required.')
    elif not plan_key.replace('_', '').replace('-', '').isalnum():
        errors.append('Plan key must contain only lowercase letters, numbers, hyphens and underscores.')
    elif Plan.query.filter_by(plan_key=plan_key).first():
        errors.append(f'Plan key "{plan_key}" already exists.')

    if errors:
        for e in errors:
            flash(e, 'error')
        return redirect(url_for('admin.plans'))

    # ── Parse numeric fields ───────────────────────────────────────
    price_usd  = float(raw_price) if raw_price else None
    shipments  = int(raw_ships)   if raw_ships  else None

    try:
        sort_order = int(sort_order)
    except ValueError:
        sort_order = 0

    plan = Plan(
        plan_key    = plan_key,
        name        = name,
        description = description,
        price_usd   = price_usd,
        interval    = interval,
        shipments   = shipments,
        is_active   = is_active,
        is_featured = is_featured,
        sort_order  = sort_order,
    )
    plan.features = features

    db.session.add(plan)
    db.session.commit()

    flash(f'Plan "{name}" created successfully.', 'success')
    return redirect(url_for('admin.plans'))


@admin_bp.route('/plans/<int:plan_id>/edit', methods=['POST'])
@login_required
@admin_required
def edit_plan(plan_id):
    """Edit an existing plan."""

    plan = Plan.query.get_or_404(plan_id)

    name        = request.form.get('name', '').strip()
    plan_key    = request.form.get('plan_key', '').strip().lower()
    raw_price   = request.form.get('price_usd', '').strip()
    raw_ships   = request.form.get('shipments', '').strip()
    interval    = request.form.get('interval', 'month').strip()
    sort_order  = request.form.get('sort_order', '0').strip()
    description = request.form.get('description', '').strip()
    is_active   = request.form.get('is_active') == 'on'
    is_featured = request.form.get('is_featured') == 'on'
    features    = [f.strip() for f in request.form.getlist('features[]') if f.strip()]

    # ── Validation ────────────────────────────────────────────────
    errors = []
    if not name:
        errors.append('Plan name is required.')
    if not plan_key:
        errors.append('Plan key is required.')
    else:
        conflict = Plan.query.filter(
            Plan.plan_key == plan_key,
            Plan.id != plan_id
        ).first()
        if conflict:
            errors.append(f'Plan key "{plan_key}" is already used by another plan.')

    if errors:
        for e in errors:
            flash(e, 'error')
        return redirect(url_for('admin.plans'))

    # ── Apply changes ──────────────────────────────────────────────
    old_key = plan.plan_key

    plan.name        = name
    plan.plan_key    = plan_key
    plan.description = description
    plan.price_usd   = float(raw_price) if raw_price else None
    plan.shipments   = int(raw_ships)   if raw_ships  else None
    plan.interval    = interval
    plan.is_active   = is_active
    plan.is_featured = is_featured
    plan.features    = features

    try:
        plan.sort_order = int(sort_order)
    except ValueError:
        plan.sort_order = 0

    # If the plan_key changed, update existing subscriptions too
    if old_key != plan_key:
        Subscription.query.filter_by(plan_id=old_key).update({'plan_id': plan_key})

    db.session.commit()

    flash(f'Plan "{name}" updated successfully.', 'success')
    return redirect(url_for('admin.plans'))


@admin_bp.route('/plans/<int:plan_id>/toggle', methods=['POST'])
@login_required
@admin_required
def toggle_plan(plan_id):
    """Toggle plan active/inactive via AJAX."""

    plan = Plan.query.get_or_404(plan_id)
    plan.is_active = not plan.is_active
    db.session.commit()

    state = 'activated' if plan.is_active else 'deactivated'
    return jsonify({
        'success': True,
        'is_active': plan.is_active,
        'message': f'Plan "{plan.name}" {state}.',
    })


@admin_bp.route('/plans/<int:plan_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_plan(plan_id):
    """
    Delete a plan.
    Blocked if any active subscriptions reference this plan.
    """

    plan = Plan.query.get_or_404(plan_id)

    active_subs = Subscription.query.filter_by(
        plan_id=plan.plan_key,
        status='active'
    ).count()

    if active_subs > 0:
        flash(
            f'Cannot delete "{plan.name}" — it has {active_subs} active subscriber(s). '
            f'Deactivate the plan or migrate subscribers first.',
            'error'
        )
        return redirect(url_for('admin.plans'))

    plan_name = plan.name
    db.session.delete(plan)
    db.session.commit()

    flash(f'Plan "{plan_name}" has been deleted.', 'success')
    return redirect(url_for('admin.plans'))




# ────────────────────────────────────────────
# Shipment Payment Management (NEW)
# ────────────────────────────────────────────

# @admin_bp.route('/shipment-payments')
# @login_required
# @admin_required
# def shipment_payments():
#     """View all shipment payments."""
#     page = request.args.get('page', 1, type=int)
#     status = request.args.get('status', 'pending').strip()
    
#     query = ShipmentPayment.query.join(Shipment).join(User, ShipmentPayment.user_id == User.id).options(
#         db.joinedload(ShipmentPayment.shipment),
#         db.joinedload(ShipmentPayment.payment_method),
#         # Remove this: db.joinedload(ShipmentPayment.user)
#         # Instead, use contains_eager if you need the user object
#     )
    
#     # Or simpler - just remove the user joinedload and query user separately when needed
#     if status != 'all':
#         query = query.filter(ShipmentPayment.status == status)
    
#     shipment_payments = query.order_by(ShipmentPayment.created_at.desc()).paginate(
#         page=page, per_page=20, error_out=False
#     )
    
#     return render_template(
#         'admin/shipment_payments.html',
#         shipment_payments=shipment_payments,
#         status=status
#     )


@admin_bp.route('/shipment-payments/<int:payment_id>')
@login_required
@admin_required
def shipment_payment_detail(payment_id):
    payment = ShipmentPayment.query.options(
        db.joinedload(ShipmentPayment.shipment),
        db.joinedload(ShipmentPayment.payment_method),
        db.joinedload(ShipmentPayment.user)
    ).get_or_404(payment_id)
    
    return render_template(
        'admin/shipment_payment_detail.html',
        payment=payment,
        shipment=payment.shipment  # ← needed for the shipment card
    )


@admin_bp.route('/shipment-payments/<int:payment_id>/verify', methods=['POST'])
@login_required
@admin_required
def verify_shipment_payment(payment_id):
    """Verify/approve shipment payment and update shipment status."""
    payment = ShipmentPayment.query.get_or_404(payment_id)
    
    if payment.status != 'pending' and payment.status != 'pending_verification':
        flash('This payment has already been processed.', 'error')
        return redirect(url_for('admin.shipment_payments'))
    
    action = request.form.get('action')  # 'approve' or 'reject'
    notes = request.form.get('notes', '').strip()
    
    if action == 'approve':
        payment.status = 'paid'
        payment.paid_at = datetime.utcnow()
        payment.payment_notes = notes
        
        # Update shipment status
        shipment = payment.shipment
        shipment.status = 'Booking Created'  # Now process the shipment
        
        # Add event
        event = ShipmentEvent(
            shipment_id=shipment.id,
            status='Payment Verified',
            location=shipment.origin,
            description='Payment verified by admin. Shipment processing begins.',
            timestamp=datetime.utcnow()
        )
        db.session.add(event)
        
        # Notify user
        notification = Notification(
            user_id=payment.user_id,
            title='Payment Verified',
            message=f'Your payment for shipment {shipment.tracking_number} has been verified. Processing begins now!',
            notification_type='payment_success',
            related_shipment_id=shipment.id,
            link=url_for('user.tracking', q=shipment.tracking_number),
            priority='high'
        )
        db.session.add(notification)
        
        flash(f'Payment approved. Shipment {shipment.tracking_number} is now being processed.', 'success')
        
    else:  # reject
        payment.status = 'failed'
        payment.payment_notes = notes
        
        # Update shipment status
        shipment = payment.shipment
        shipment.status = 'Payment Failed'
        
        # Notify user
        notification = Notification(
            user_id=payment.user_id,
            title='Payment Verification Failed',
            message=f'Your payment for shipment {shipment.tracking_number} was rejected. Reason: {notes}',
            notification_type='payment_failed',
            related_shipment_id=shipment.id,
            link=url_for('user.support'),
            priority='urgent'
        )
        db.session.add(notification)
        
        flash('Payment rejected. User has been notified.', 'warning')
    
    db.session.commit()
    return redirect(url_for('admin.shipment_payment_detail', payment_id=payment_id))


# ────────────────────────────────────────────
# Payment Method Management (UPDATED)
# ────────────────────────────────────────────

@admin_bp.route('/all-payments')
@login_required
@admin_required
def all_payments():
    """Unified view: plan upgrade payments + shipment payments."""
    page         = request.args.get('page', 1, type=int)
    type_filter  = request.args.get('type', 'all').strip()   # all | plan | shipment
    status_filter= request.args.get('status', 'all').strip()
    search       = request.args.get('q', '').strip()

    per_page = 20

    # ── Build plan-upgrade list ──────────────────────────────────
    plan_items = []
    if type_filter in ('all', 'plan'):
        plan_q = PaymentRequest.query.join(
            User, PaymentRequest.user_id == User.id
        )
        if status_filter != 'all':
            plan_q = plan_q.filter(PaymentRequest.status == status_filter)
        if search:
            plan_q = plan_q.filter(
                db.or_(
                    User.full_name.ilike(f'%{search}%'),
                    User.email.ilike(f'%{search}%'),
                    PaymentRequest.requested_plan_name.ilike(f'%{search}%'),
                )
            )
        for pr in plan_q.all():
            plan_items.append({
                'type':       'plan',
                'obj':        pr,
                'user':       pr.user,
                'amount':     pr.amount_usd,
                'status':     pr.status,
                'method':     pr.payment_method,
                'created_at': pr.created_at,
            })

    # ── Build shipment-payment list ──────────────────────────────
    ship_items = []
    if type_filter in ('all', 'shipment'):
        ship_q = (
            ShipmentPayment.query
            .join(Shipment, ShipmentPayment.shipment_id == Shipment.id)
            .join(User,     ShipmentPayment.user_id     == User.id)
        )
        if status_filter != 'all':
            ship_q = ship_q.filter(ShipmentPayment.status == status_filter)
        if search:
            ship_q = ship_q.filter(
                db.or_(
                    User.full_name.ilike(f'%{search}%'),
                    User.email.ilike(f'%{search}%'),
                    Shipment.tracking_number.ilike(f'%{search}%'),
                    Shipment.origin.ilike(f'%{search}%'),
                    Shipment.destination.ilike(f'%{search}%'),
                )
            )
        for sp in ship_q.all():
            ship_items.append({
                'type':       'shipment',
                'obj':        sp,
                'user':       sp.user,
                'amount':     sp.amount,
                'status':     sp.status,
                'method':     sp.payment_method,
                'created_at': sp.created_at,
            })

    # ── Merge and sort by date descending ───────────────────────
    all_items = sorted(plan_items + ship_items, key=lambda x: x['created_at'], reverse=True)

    # ── Paginate manually ────────────────────────────────────────
    total       = len(all_items)
    total_pages = max(1, (total + per_page - 1) // per_page)
    current_page= max(1, min(page, total_pages))
    start       = (current_page - 1) * per_page
    payments    = all_items[start: start + per_page]

    # ── Summary stats ────────────────────────────────────────────
    total_revenue = (
        db.session.query(func.sum(PaymentRequest.amount_usd))
        .filter(PaymentRequest.status == 'approved').scalar() or 0
    ) + (
        db.session.query(func.sum(ShipmentPayment.amount))
        .filter(ShipmentPayment.status == 'paid').scalar() or 0
    )

    stats = {
        'total_revenue':    total_revenue,
        'pending_count':    (
            PaymentRequest.query.filter_by(status='pending').count() +
            ShipmentPayment.query.filter(
                ShipmentPayment.status.in_(['pending', 'pending_verification'])
            ).count()
        ),
        'plan_count':       PaymentRequest.query.count(),
        'shipment_count':   ShipmentPayment.query.count(),
        'pending_plan':     PaymentRequest.query.filter_by(status='pending').count(),
        'pending_shipment': ShipmentPayment.query.filter(
            ShipmentPayment.status.in_(['pending', 'pending_verification'])
        ).count(),
    }

    return render_template(
        'admin/all_payments.html',
        payments=payments,
        stats=stats,
        type_filter=type_filter,
        status_filter=status_filter,
        search=search,
        current_page=current_page,
        total_pages=total_pages,
    )



@admin_bp.route('/payments')
@login_required
@admin_required
def payments():
    return redirect(url_for('admin.all_payments', type='plan', status='pending'))

@admin_bp.route('/shipment-payments')
@login_required
@admin_required
def shipment_payments():
    return redirect(url_for('admin.all_payments', type='shipment', status='pending'))


@admin_bp.route('/live-chat')
@login_required
@admin_required
def live_chat_dashboard():
    """Live chat support dashboard for admins"""
    return render_template('admin/chat_dashboard.html')

@admin_bp.route('/api/chat/history')
@login_required
@admin_required
def chat_history():
    """Get chat history for a specific session"""
    session_id = request.args.get('session_id', type=int)
    if not session_id:
        return jsonify({'error': 'Session ID required'}), 400
    
    session = LiveChatSession.query.get_or_404(session_id)
    return jsonify({
        'session': {
            'id': session.id,
            'status': session.status,
            'user': {
                'id': session.user_id,
                'name': session.user.full_name or session.user.email,
                'email': session.user.email
            }
        },
        'messages': [m.to_dict() for m in session.messages]
    })

@admin_bp.route('/api/chat/sessions')
@login_required
@admin_required
def chat_sessions():
    """Get all chat sessions with filtering"""
    status = request.args.get('status', 'all')
    page = request.args.get('page', 1, type=int)
    
    query = LiveChatSession.query
    
    if status != 'all':
        query = query.filter_by(status=status)
    
    sessions = query.order_by(LiveChatSession.created_at.desc()).paginate(
        page=page, per_page=20, error_out=False
    )
    
    return jsonify({
        'sessions': [{
            'id': s.id,
            'status': s.status,
            'user_name': s.user.full_name or s.user.email,
            'subject': s.subject,
            'created_at': s.created_at.isoformat(),
            'message_count': len(s.messages),
            'admin_name': s.admin.full_name if s.admin else None
        } for s in sessions.items],
        'pages': sessions.pages,
        'current_page': sessions.page
    })