"""
models.py — UTHAO database models
"""

from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime, timedelta
from extensions import db, mail, login_manager, migrate
from flask import url_for



# Supported currencies with symbols - REMOVED NGN, added USDT
CURRENCIES = {
    'USD': {'symbol': '$', 'name': 'US Dollar'},
    'GBP': {'symbol': '£', 'name': 'British Pound'},
    'USDT': {'symbol': '₮', 'name': 'Tether USD'},
    'EUR': {'symbol': '€', 'name': 'Euro'},
}

# Exchange rates (USD base) - REMOVED NGN
EXCHANGE_RATES = {
    'USD': 1.0,
    'GBP': 0.79,
    'USDT': 1.0,  # Stablecoin pegged to USD
    'EUR': 0.92,
}

# ─────────────────────────────────────────────
# Plan catalogue — prices in USD (base currency)
# ADDED: Basic and Business plans
# ─────────────────────────────────────────────
PLANS = {
    'free': {
        'id':        'free',
        'name':      'Free',
        'price_usd': 0,
        'interval':  'month',
        'shipments': 3,
        'features':  [
            'Up to 3 shipments / month',
            'Basic tracking',
            'Email support',
            'Limited API access',
        ],
    },
    'starter': {
        'id':        'starter',
        'name':      'Starter',
        'price_usd': 9,
        'interval':  'month',
        'shipments': 10,
        'features':  [
            'Up to 10 shipments / month',
            'Basic tracking',
            'Email support',
            'Standard API access',
        ],
    },
    'basic': {  # NEW PLAN
        'id':        'basic',
        'name':      'Basic',
        'price_usd': 19,
        'interval':  'month',
        'shipments': 25,
        'features':  [
            'Up to 25 shipments / month',
            'Advanced tracking',
            'Priority email support',
            'Full API access',
            'Basic analytics',
        ],
    },
    'professional': {
        'id':        'professional',
        'name':      'Professional',
        'price_usd': 49,
        'interval':  'month',
        'shipments': 100,
        'features':  [
            'Up to 100 shipments / month',
            'Priority tracking',
            'Phone & email support',
            'Advanced analytics dashboard',
            'Webhook notifications',
        ],
    },
    'business': {  # NEW PLAN
        'id':        'business',
        'name':      'Business',
        'price_usd': 99,
        'interval':  'month',
        'shipments': 500,
        'features':  [
            'Up to 500 shipments / month',
            'Real-time tracking',
            '24/7 Priority support',
            'Custom integrations',
            'Advanced analytics & reporting',
            'Multi-user access (5 seats)',
        ],
    },
    'enterprise': {
        'id':        'enterprise',
        'name':      'Enterprise',
        'price_usd': None,
        'interval':  'month',
        'shipments': None,
        'features':  [
            'Unlimited shipments',
            'Everything in Business',
            'Dedicated account manager',
            'Custom API integrations',
            'SLA guarantee',
            'White-label options',
            'Multi-user access (unlimited)',
        ],
    },
}


class User(UserMixin, db.Model):
    __tablename__ = 'user'

    id            = db.Column(db.Integer, primary_key=True)
    email         = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    full_name     = db.Column(db.String(100), nullable=False)
    company       = db.Column(db.String(100))
    phone         = db.Column(db.String(20))
    is_admin      = db.Column(db.Boolean, default=False)
    bio           = db.Column(db.Text)
    
    avatar_url    = db.Column(db.String(500))
    two_fa_enabled = db.Column(db.Boolean, default=False)
    two_fa_secret = db.Column(db.String(32))
    currency      = db.Column(db.String(4), default='USD', nullable=False)  # Changed to 4 chars for USDT

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)  # For soft delete

    shipments = db.relationship(
        'Shipment', backref='customer', lazy=True,
        order_by='Shipment.created_at.desc()'
    )
    subscription = db.relationship(
        'Subscription', backref='user', uselist=False, lazy=True
    )
    notification_prefs = db.relationship(
        'NotificationPreference', backref='user', uselist=False, lazy=True,
        cascade='all, delete-orphan'
    )
    payment_requests = db.relationship(
        'PaymentRequest', 
        foreign_keys='PaymentRequest.user_id',
        backref='user', 
        lazy=True,
        order_by='PaymentRequest.created_at.desc()'
    )

    @property
    def active_plan(self):
        plan_key = self.subscription.plan_id if self.subscription else 'free'
        plan = Plan.query.filter_by(plan_key=plan_key).first()
        if plan:
            return plan
        # fallback stub before seeding
        stub = Plan(plan_key='free', name='Free', price_usd=0, shipments=3, is_active=True)
        stub._features = '["Basic access"]'
        return stub
    
    def get_notification_prefs(self):
        if not self.notification_prefs:
            prefs = NotificationPreference(user_id=self.id)
            db.session.add(prefs)
            db.session.commit()
            return prefs
        return self.notification_prefs
    
    def get_price_display(self, price_usd):
        """Convert USD price to user's preferred currency."""
        if price_usd is None:
            return 'Custom'
        if price_usd == 0:
            return 'Free'
        
        currency = self.currency if self.currency else 'USD'
        if currency not in CURRENCIES:
            currency = 'USD'
            
        rate = EXCHANGE_RATES.get(currency, 1.0)
        converted = price_usd * rate
        symbol = CURRENCIES[currency]['symbol']
        
        # Format based on currency type
        if currency == 'USDT':
            return f"{symbol}{converted:.2f}"
        else:
            return f"{symbol}{converted:.2f}"
    
    def get_plan_price(self, plan_id):
        """Get formatted price for a specific plan in user's currency."""
        plan = PLANS.get(plan_id)
        if not plan:
            return 'Custom'
        return self.get_price_display(plan['price_usd'])
    
    def get_pending_payment_request(self, plan_id=None):
        """Get pending payment request for a plan."""
        query = PaymentRequest.query.filter_by(
            user_id=self.id, 
            status='pending'
        )
        if plan_id:
            query = query.filter_by(requested_plan_id=plan_id)
        return query.first()
    
    def can_downgrade_free(self, target_plan_id):
        """Check if user can downgrade to free plan without payment."""
        target_plan = PLANS.get(target_plan_id)
        if not target_plan:
            return False
        return target_plan['price_usd'] == 0

    def __repr__(self):
        return f'<User {self.email}>'


class PackageImage(db.Model):
    """Images uploaded for packages/items"""
    id = db.Column(db.Integer, primary_key=True)
    package_id = db.Column(db.Integer, db.ForeignKey('package.id'), nullable=False)
    image_url = db.Column(db.String(500), nullable=False)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    package = db.relationship('Package', backref='images')

class ShipmentPayment(db.Model):
    """Payment records for shipments"""
    id = db.Column(db.Integer, primary_key=True)
    shipment_id = db.Column(db.Integer, db.ForeignKey('shipment.id'), nullable=False, unique=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    amount = db.Column(db.Float, nullable=False)
    currency = db.Column(db.String(3), default='USD')
    
    payment_method_id = db.Column(db.Integer, db.ForeignKey('payment_method.id'), nullable=False)
    payment_method = db.relationship('PaymentMethod')
    
    status = db.Column(db.String(20), default='pending')  # pending, paid, failed, refunded
    receipt_url = db.Column(db.String(500))
    transaction_id = db.Column(db.String(100))
    payment_notes = db.Column(db.Text)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    paid_at = db.Column(db.DateTime)

    user = db.relationship('User', backref='shipment_payments')
        
    shipment = db.relationship('Shipment', backref=db.backref('payment', uselist=False))


class PaymentMethod(db.Model):
    """Admin-configurable payment methods"""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)  # "Bitcoin", "Bank Transfer", "PayPal"
    code = db.Column(db.String(20), nullable=False, unique=True)  # "btc", "bank_gbp", "paypal"
    display_name = db.Column(db.String(100))
    
    # Method type: crypto, bank_transfer, paypal, etc.
    method_type = db.Column(db.String(20), nullable=True)
    
    # Configuration JSON for method-specific details
    config = db.Column(db.JSON, default=dict, nullable=True)  # Changed from default={}
    """
    For crypto: {"address": "...", "network": "...", "qr_code_url": "..."}
    For bank: {"account_name": "...", "account_number": "...", "bank_name": "...", "swift": "...", "reference_format": "..."}
    For paypal: {"email": "...", "link": "..."}
    """
    
    is_active = db.Column(db.Boolean, default=True)
    sort_order = db.Column(db.Integer, default=0)
    icon = db.Column(db.String(50), default='fa-money-bill')
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def get_instructions(self, amount, reference):
        """Generate payment instructions based on method type"""
        if self.method_type == 'crypto':
            return {
                'type': 'crypto',
                'address': self.config.get('address'),
                'network': self.config.get('network', 'TRC20'),
                'amount': amount,
                'reference': reference,
                'qr_code': self.config.get('qr_code_url'),
                'instructions': f"Send exactly {amount} USDT to the address above. Include reference: {reference}"
            }
        elif self.method_type == 'bank_transfer':
            return {
                'type': 'bank',
                'account_name': self.config.get('account_name'),
                'account_number': self.config.get('account_number'),
                'bank_name': self.config.get('bank_name'),
                'swift_code': self.config.get('swift'),
                'reference': reference,
                'instructions': f"Transfer to {self.config.get('bank_name')}. Use reference: {reference}"
            }
        elif self.method_type == 'paypal':
            return {
                'type': 'paypal',
                'email': self.config.get('email'),
                'link': self.config.get('link'),
                'amount': amount,
                'instructions': f"Send {amount} to {self.config.get('email')} or use the link below"
            }
        return {}


    def to_dict(self):
        return {
            'id':           self.id,
            'name':         self.name or '',
            'code':         self.code or '',
            'display_name': self.display_name or '',
            'method_type':  self.method_type or 'crypto',
            'config':       self.config or {},   # never None
            'icon':         self.icon or '',
            'sort_order':   self.sort_order or 0,
            'is_active':    bool(self.is_active),
        }


class PaymentRequest(db.Model):
    __tablename__ = 'payment_request'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    requested_plan_id = db.Column(db.String(30), nullable=False)
    requested_plan_name = db.Column(db.String(50), nullable=False)
    
    amount_usd = db.Column(db.Float, nullable=False)
    amount_display = db.Column(db.String(100), nullable=False)
    
    payment_method_id = db.Column(db.Integer, db.ForeignKey('payment_method.id'))
    payment_method = db.relationship('PaymentMethod', backref='payment_requests')
    
    payment_proof_url = db.Column(db.String(500))
    payment_notes = db.Column(db.Text)
    
    status = db.Column(db.String(20), default='pending', nullable=False)
    
    reviewed_by_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    reviewed_at = db.Column(db.DateTime)
    review_notes = db.Column(db.Text)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime)
    
    @property
    def is_expired(self):
        if self.expires_at:
            return datetime.utcnow() > self.expires_at
        return False
    
    def approve(self, admin_user_id, notes=None):
        self.status = 'approved'
        self.reviewed_by_id = admin_user_id
        self.reviewed_at = datetime.utcnow()
        self.review_notes = notes
        
        sub = self.user.subscription
        if not sub:
            sub = Subscription(user_id=self.user.id)
            db.session.add(sub)
        
        sub.change_plan(self.requested_plan_id)
        
    def reject(self, admin_user_id, notes=None):
        self.status = 'rejected'
        self.reviewed_by_id = admin_user_id
        self.reviewed_at = datetime.utcnow()
        self.review_notes = notes


# class NotificationPreference(db.Model):
#     __tablename__ = 'notification_preference'
    
#     id = db.Column(db.Integer, primary_key=True)
#     user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, unique=True)
    
#     email_notif = db.Column(db.Boolean, default=True)
#     notif_booking = db.Column(db.Boolean, default=True)
#     notif_status = db.Column(db.Boolean, default=True)
#     notif_otd = db.Column(db.Boolean, default=True)
#     notif_delivered = db.Column(db.Boolean, default=True)
#     notif_delays = db.Column(db.Boolean, default=True)
#     notif_news = db.Column(db.Boolean, default=False)
#     sms_notif = db.Column(db.Boolean, default=False)
    
#     updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Subscription(db.Model):
    __tablename__ = 'subscription'

    id      = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'),
                        nullable=False, unique=True)

    plan_id = db.Column(db.String(30), default='free', nullable=False)  # Changed default to free
    status  = db.Column(db.String(20), default='active', nullable=False)

    started_at = db.Column(db.DateTime, default=datetime.utcnow)
    renews_at  = db.Column(db.DateTime)

    previous_plan_id = db.Column(db.String(30))
    changed_at       = db.Column(db.DateTime)

    @property
    def plan(self):
        p = Plan.query.filter_by(plan_key=self.plan_id).first()
        if p:
            return p
        stub = Plan(plan_key=self.plan_id, name=self.plan_id.title(), price_usd=0, is_active=True)
        return stub

    @property
    def is_active(self):
        return self.status == 'active'

    def change_plan(self, new_plan_id):
        if new_plan_id not in PLANS:
            raise ValueError(f'Unknown plan: {new_plan_id}')
        self.previous_plan_id = self.plan_id
        self.changed_at       = datetime.utcnow()
        self.plan_id          = new_plan_id
        self.status           = 'active'
        plan = PLANS[new_plan_id]
        # Only set renews_at for paid plans
        self.renews_at = (
            datetime.utcnow() + timedelta(days=30)
            if plan['price_usd'] and plan['price_usd'] > 0 else None
        )

    def __repr__(self):
        return f'<Subscription user={self.user_id} plan={self.plan_id}>'


class Shipment(db.Model):
    __tablename__ = 'shipment'

    id              = db.Column(db.Integer, primary_key=True)
    tracking_number = db.Column(db.String(20), unique=True, nullable=False)
    user_id         = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    origin      = db.Column(db.String(200), nullable=False)
    destination = db.Column(db.String(200), nullable=False)

    sender_name  = db.Column(db.String(100))
    sender_phone = db.Column(db.String(30))

    receiver_name    = db.Column(db.String(100))
    receiver_phone   = db.Column(db.String(30))
    receiver_company = db.Column(db.String(100))

    weight     = db.Column(db.Float)
    dimensions = db.Column(db.String(100))
    commodity  = db.Column(db.String(100))

    service_level = db.Column(db.String(20))
    cost          = db.Column(db.Float)

    status             = db.Column(db.String(50), default='Booking Created')
    created_at         = db.Column(db.DateTime, default=datetime.utcnow)
    estimated_delivery = db.Column(db.DateTime)

    packages = db.relationship(
        'Package', backref='shipment', lazy=True,
        cascade='all, delete-orphan'
    )
    events = db.relationship(
        'ShipmentEvent', backref='shipment', lazy=True,
        order_by='ShipmentEvent.timestamp.desc()',
        cascade='all, delete-orphan'
    )

    def __repr__(self):
        return f'<Shipment {self.tracking_number}>'


class Package(db.Model):
    __tablename__ = 'package'

    id          = db.Column(db.Integer, primary_key=True)
    shipment_id = db.Column(db.Integer, db.ForeignKey('shipment.id'), nullable=False)

    length = db.Column(db.Float)
    width  = db.Column(db.Float)
    height = db.Column(db.Float)
    weight = db.Column(db.Float)

    description = db.Column(db.String(200))
    stackable   = db.Column(db.Boolean, default=False)
    fragile     = db.Column(db.Boolean, default=False)

    def __repr__(self):
        return f'<Package {self.id} -> Shipment {self.shipment_id}>'

    @property
    def volume_cbm(self):
        if self.length and self.width and self.height:
            return (self.length * self.width * self.height) / 1_000_000
        return 0.0

    @property
    def dimensions_str(self):
        return f'{self.length}x{self.width}x{self.height} cm'


class ShipmentEvent(db.Model):
    __tablename__ = 'shipment_event'

    id          = db.Column(db.Integer, primary_key=True)
    shipment_id = db.Column(db.Integer, db.ForeignKey('shipment.id'), nullable=False)
    status      = db.Column(db.String(100))
    location    = db.Column(db.String(200))
    description = db.Column(db.Text)
    timestamp   = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<ShipmentEvent {self.status} @ {self.timestamp}>'



# ─────────────────────────────────────────────
# Support Ticket System
# ─────────────────────────────────────────────

class SupportTicket(db.Model):
    __tablename__ = 'support_ticket'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    # Ticket details
    subject = db.Column(db.String(200), nullable=False)
    category = db.Column(db.String(50), nullable=False)  # general, billing, technical, shipment
    priority = db.Column(db.String(20), default='medium')  # low, medium, high, urgent
    message = db.Column(db.Text, nullable=False)
    shipment_reference = db.Column(db.String(50))  # Optional tracking number
    
    # Status tracking
    status = db.Column(db.String(20), default='open')  # open, in_progress, resolved, closed
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    resolved_at = db.Column(db.DateTime)
    
    user = db.relationship('User', backref='support_tickets', lazy=True)
    
    # Relations
    replies = db.relationship('TicketReply', backref='ticket', lazy=True, order_by='TicketReply.created_at.asc()')
    
    @property
    def status_color(self):
        colors = {
            'open': '#3b82f6',
            'in_progress': '#f59e0b',
            'resolved': '#22c55e',
            'closed': '#6b7280'
        }
        return colors.get(self.status, '#6b7280')
    
    @property
    def status_label(self):
        labels = {
            'open': 'Open',
            'in_progress': 'In Progress',
            'resolved': 'Resolved',
            'closed': 'Closed'
        }
        return labels.get(self.status, self.status.title())
    
    @property
    def customer(self):
        """Get user who created this ticket."""
        return User.query.get(self.user_id)

    def __repr__(self):
        return f'<SupportTicket #{self.id}: {self.subject}>'


class TicketReply(db.Model):
    __tablename__ = 'ticket_reply'
    
    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.Integer, db.ForeignKey('support_ticket.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    message = db.Column(db.Text, nullable=False)
    is_staff = db.Column(db.Boolean, default=False)  # True if from support team
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relations
    user = db.relationship('User', backref='ticket_replies')
    
    def __repr__(self):
        return f'<TicketReply #{self.id} on Ticket #{self.ticket_id}>'


# ─────────────────────────────────────────────
# Notification System
# ─────────────────────────────────────────────

class Notification(db.Model):
    __tablename__ = 'notification'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    
    # Notification content
    title = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text, nullable=False)
    notification_type = db.Column(db.String(50), nullable=False)  # shipment, billing, system, promotional
    
    # Related entities (optional)
    related_shipment_id = db.Column(db.Integer, db.ForeignKey('shipment.id'))
    related_ticket_id = db.Column(db.Integer, db.ForeignKey('support_ticket.id'))
    link = db.Column(db.String(500))  # URL to navigate when clicked
    
    # Status
    is_read = db.Column(db.Boolean, default=False, index=True)
    is_archived = db.Column(db.Boolean, default=False)
    
    # Priority
    priority = db.Column(db.String(20), default='normal')  # low, normal, high, urgent
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    read_at = db.Column(db.DateTime)
    
    # Relations
    user = db.relationship('User', backref='notifications')
    related_shipment = db.relationship('Shipment')
    
    @property
    def icon(self):
        icons = {
            'shipment': 'fa-box',
            'shipment_delivered': 'fa-check-circle',
            'shipment_transit': 'fa-shipping-fast',
            'billing': 'fa-credit-card',
            'payment_success': 'fa-check-circle',
            'payment_failed': 'fa-exclamation-circle',
            'plan_change': 'fa-arrow-up',
            'system': 'fa-cog',
            'support': 'fa-headset',
            'ticket_reply': 'fa-reply',
            'promotional': 'fa-bullhorn',
            'security': 'fa-shield-alt'
        }
        return icons.get(self.notification_type, 'fa-bell')
    
    @property
    def color(self):
        colors = {
            'shipment': '#3b82f6',
            'shipment_delivered': '#22c55e',
            'shipment_transit': '#f59e0b',
            'billing': '#8b5cf6',
            'payment_success': '#22c55e',
            'payment_failed': '#ef4444',
            'plan_change': '#f97316',
            'system': '#6b7280',
            'support': '#3b82f6',
            'ticket_reply': '#3b82f6',
            'promotional': '#f59e0b',
            'security': '#ef4444'
        }
        return colors.get(self.notification_type, '#6b7280')
    
    @property
    def time_ago(self):
        from datetime import datetime
        diff = datetime.utcnow() - self.created_at
        seconds = diff.total_seconds()
        
        if seconds < 60:
            return 'Just now'
        elif seconds < 3600:
            return f'{int(seconds // 60)}m ago'
        elif seconds < 86400:
            return f'{int(seconds // 3600)}h ago'
        elif seconds < 604800:
            return f'{int(seconds // 86400)}d ago'
        else:
            return self.created_at.strftime('%d %b')
    
    def mark_as_read(self):
        if not self.is_read:
            self.is_read = True
            self.read_at = datetime.utcnow()
    
    def __repr__(self):
        return f'<Notification {self.id}: {self.title}>'




class NotificationPreference(db.Model):
    __tablename__ = 'notification_preference'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, unique=True)
    
    email_notif = db.Column(db.Boolean, default=True)
    notif_booking = db.Column(db.Boolean, default=True)
    notif_status = db.Column(db.Boolean, default=True)
    notif_otd = db.Column(db.Boolean, default=True)
    notif_delivered = db.Column(db.Boolean, default=True)
    notif_delays = db.Column(db.Boolean, default=True)
    notif_news = db.Column(db.Boolean, default=False)
    sms_notif = db.Column(db.Boolean, default=False)
    
    # Email notifications
    email_shipment_updates = db.Column(db.Boolean, default=True)
    email_billing = db.Column(db.Boolean, default=True)
    email_promotions = db.Column(db.Boolean, default=False)
    email_security = db.Column(db.Boolean, default=True)
    
    # In-app notifications
    app_shipment_updates = db.Column(db.Boolean, default=True)
    app_billing = db.Column(db.Boolean, default=True)
    app_promotions = db.Column(db.Boolean, default=True)
    app_security = db.Column(db.Boolean, default=True)
    
    # Push notifications (future)
    push_enabled = db.Column(db.Boolean, default=False)

    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    


# Example: Create notification when shipment status changes
def notify_shipment_update(shipment, old_status, new_status):
    """Create notification for shipment status change."""
    title = f'Shipment {new_status}'
    message = f'Your shipment {shipment.tracking_number} is now {new_status}.'
    notif_type = f'shipment_{new_status.lower().replace(" ", "_")}'
    
    link = url_for('user.tracking', q=shipment.tracking_number)
    
    create_notification(
        user_id=shipment.user_id,
        title=title,
        message=message,
        notification_type=notif_type,
        related_shipment_id=shipment.id,
        link=link,
        priority='high' if new_status == 'Delivered' else 'normal'
    )

# Example: Notify on ticket reply
def notify_ticket_reply(ticket, reply):
    """Notify user of support ticket reply."""
    if reply.is_staff:
        create_notification(
            user_id=ticket.user_id,
            title='New Support Reply',
            message=f'Support responded to: {ticket.subject}',
            notification_type='ticket_reply',
            related_ticket_id=ticket.id,
            link=url_for('user.view_ticket', ticket_id=ticket.id),
            priority='normal'
        )


import json as _json

class Plan(db.Model):
    """
    DB-backed plan catalogue.
    Replaces the hardcoded PLANS dict for admin-managed plans.
    The PLANS dict in models.py is kept as a fallback/seed reference.
    """
    __tablename__ = 'plan'

    id          = db.Column(db.Integer, primary_key=True)
    plan_key    = db.Column(db.String(30), unique=True, nullable=False)   # e.g. 'professional'
    name        = db.Column(db.String(50), nullable=False)                # e.g. 'Professional'
    description = db.Column(db.Text)

    price_usd   = db.Column(db.Float, nullable=True)   # None = custom/contact us
    interval    = db.Column(db.String(10), default='month', nullable=False)
    shipments   = db.Column(db.Integer, nullable=True)  # None = unlimited

    # Features stored as JSON array string e.g. '["Feature A", "Feature B"]'
    _features   = db.Column('features', db.Text, default='[]')

    is_active   = db.Column(db.Boolean, default=True, nullable=False)
    is_featured = db.Column(db.Boolean, default=False, nullable=False)  # "Recommended" badge
    sort_order  = db.Column(db.Integer, default=0, nullable=False)

    created_at  = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at  = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # ── features property ────────────────────────────────────────────
    @property
    def features(self):
        try:
            return _json.loads(self._features or '[]')
        except (ValueError, TypeError):
            return []

    @features.setter
    def features(self, value):
        self._features = _json.dumps(value if isinstance(value, list) else [])

    # ── Convenience: dict representation (mirrors old PLANS dict) ───
    def to_dict(self):
        return {
            'id':          self.id,
            'plan_key':    self.plan_key,
            'name':        self.name,
            'description': self.description,
            'price_usd':   self.price_usd,
            'interval':    self.interval,
            'shipments':   self.shipments,
            'features':    self.features,
            'is_active':   self.is_active,
            'is_featured': self.is_featured,
            'sort_order':  self.sort_order,
        }

    @property
    def subscribers_sample(self):
        """True if there are any subscribers — used for delete guard in template."""
        return Subscription.query.filter_by(plan_id=self.plan_key).first() is not None

    @property
    def active_subscriber_count(self):
        return Subscription.query.filter_by(
            plan_id=self.plan_key, status='active'
        ).count()

    @property
    def monthly_revenue(self):
        return (self.price_usd or 0) * self.active_subscriber_count

    @property
    def is_free(self):
        return self.price_usd is not None and self.price_usd == 0

    @property
    def is_custom(self):
        return self.price_usd is None

    def __repr__(self):
        return f'<Plan {self.plan_key} ${self.price_usd}>'



# Add these to your models.py

class LiveChatSession(db.Model):
    """Live chat sessions between users and admins"""
    __tablename__ = 'live_chat_session'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    admin_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)  # Assigned admin
    
    status = db.Column(db.String(20), default='waiting')  # waiting, active, closed, resolved
    subject = db.Column(db.String(200), nullable=True)  # Optional subject/topic
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    closed_at = db.Column(db.DateTime)
    
    # Relations
    user = db.relationship('User', foreign_keys=[user_id], backref='chat_sessions')
    admin = db.relationship('User', foreign_keys=[admin_id], backref='assigned_chats')
    messages = db.relationship('LiveChatMessage', backref='session', lazy=True, 
                               order_by='LiveChatMessage.created_at.asc()',
                               cascade='all, delete-orphan')
    is_ai_chat = db.Column(db.Boolean, default=False, nullable=False, server_default='0')  
    
    @property
    def unread_count_admin(self):
        """Count unread messages for admin (from user)"""
        return LiveChatMessage.query.filter_by(
            session_id=self.id, 
            is_from_user=True,
            is_read=False
        ).count()
    
    @property
    def unread_count_user(self):
        """Count unread messages for user (from admin)"""
        return LiveChatMessage.query.filter_by(
            session_id=self.id,
            is_from_user=False,
            is_read=False
        ).count()
    
    @property
    def last_message(self):
        """Get last message in session"""
        return LiveChatMessage.query.filter_by(session_id=self.id).order_by(
            LiveChatMessage.created_at.desc()
        ).first()
    
    @property
    def status_color(self):
        colors = {
            'waiting': '#f59e0b',    # amber
            'active': '#22c55e',     # green
            'closed': '#6b7280',     # gray
            'resolved': '#3b82f6'    # blue
        }
        return colors.get(self.status, '#6b7280')


    def to_dict(self, requesting_admin_id=None):
        return {
            'id': self.id,
            'user': {
                'name': self.user.full_name or self.user.email,
                'id': self.user_id
            } if self.user else None,
            'admin': {
                'name': self.admin.full_name or self.admin.email,
                'id': self.admin_id
            } if self.admin else None,
            'subject': self.subject,
            'status': self.status,
            'wait_time': int((datetime.utcnow() - self.created_at).total_seconds() / 60) if self.status == 'waiting' else 0,
            'unread': self.unread_count_admin if requesting_admin_id and self.admin_id == requesting_admin_id else 0,
            'message_count': len(self.messages),
            'last_message': self.last_message.message if self.last_message else None,
            'last_activity': self.last_message.created_at.isoformat() if self.last_message else self.updated_at.isoformat(),
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
            'is_ai_chat': self.is_ai_chat,
            'closed_at': self.closed_at.isoformat() if self.closed_at else None,
        }


class LiveChatMessage(db.Model):
    """Individual chat messages"""
    __tablename__ = 'live_chat_message'
    
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('live_chat_session.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)    
    
    message = db.Column(db.Text, nullable=False)
    is_from_user = db.Column(db.Boolean, default=True)  # True if from customer, False if from admin
    is_ai = db.Column(db.Boolean, default=False)
    
    is_read = db.Column(db.Boolean, default=False)
    read_at = db.Column(db.DateTime)
    new_message = db.Column(db.Text, nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relations
    sender = db.relationship('User', backref='chat_messages')
    
    def mark_as_read(self):
        if not self.is_read:
            self.is_read = True
            self.read_at = datetime.utcnow()
    
    @property
    def time_ago(self):
        from datetime import datetime
        diff = datetime.utcnow() - self.created_at
        seconds = diff.total_seconds()
        
        if seconds < 60:
            return 'Just now'
        elif seconds < 3600:
            return f'{int(seconds // 60)}m ago'
        elif seconds < 86400:
            return f'{int(seconds // 3600)}h ago'
        else:
            return self.created_at.strftime('%d %b %H:%M')


    # In LiveChatMessage class
    def to_dict(self):
        return {
            'id':           self.id,
            'session_id':   self.session_id,
            'message':      self.message,
            'is_from_user': self.is_from_user,
            'sender_name':  self.sender.full_name or self.sender.email if self.sender else 'Unknown',
            'is_read':      self.is_read,
            'created_at':   self.created_at.isoformat(),
            'time_ago':     self.time_ago,
        }