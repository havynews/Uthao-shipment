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
from datetime import datetime, timedelta
from sqlalchemy import func
import json

from models import (
    User, Shipment, ShipmentEvent, Package, Subscription, 
    PaymentRequest, PaymentMethod, SupportTicket, TicketReply, ShipmentPayment,
    Notification, Plan, PLANS, CURRENCIES
)

from extensions import db, mail, login_manager, migrate

from notification import create_notification



admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

# ────────────────────────────────────────────
# Decorators
# ────────────────────────────────────────────

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
    
    chart_labels = [
        datetime.strptime(d[0], '%Y-%m-%d').strftime('%d %b')
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

@admin_bp.route('/shipments/<int:shipment_id>')
@login_required
@admin_required
def shipment_detail(shipment_id):
    """View shipment details."""
    shipment = Shipment.query.get_or_404(shipment_id)
    return render_template('admin/shipment_detail.html', shipment=shipment)

@admin_bp.route('/shipments/<int:shipment_id>/update-status', methods=['POST'])
@login_required
@admin_required
def update_shipment_status(shipment_id):
    """Update shipment status and notify user."""
    shipment = Shipment.query.get_or_404(shipment_id)
    
    new_status = request.form.get('status')
    location = request.form.get('location', '').strip()
    description = request.form.get('description', '').strip()
    
    if not new_status:
        flash('Status is required.', 'error')
        return redirect(url_for('admin.shipment_detail', shipment_id=shipment.id))
    
    old_status = shipment.status
    shipment.status = new_status
    
    # Add event
    event = ShipmentEvent(
        shipment_id=shipment.id,
        status=new_status,
        location=location,
        description=description or f'Status updated to {new_status}',
        timestamp=datetime.utcnow()
    )
    db.session.add(event)
    
    # Create notification for user
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
    
    flash(f'Shipment status updated to {new_status}.', 'success')
    return redirect(url_for('admin.shipment_detail', shipment_id=shipment.id))

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