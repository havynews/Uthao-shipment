# socket_events.py
from flask_socketio import SocketIO, emit, join_room, leave_room
from flask_login import current_user
from flask import request
from functools import wraps
from datetime import datetime

socketio = None


def init_socket_events(sio):
    global socketio
    socketio = sio
    _register_events(sio)


# Topics that get AI responses
AI_TOPICS = {'General Inquiry', 'Account Help', 'Billing Question'}
# Topics that go straight to admin
ADMIN_TOPICS = {'Shipment Issue', 'Technical Support'}



import re

# ── Hardcoded Q&A Knowledge Base ─────────────────────────────────────────────

KNOWLEDGE_BASE = [

    # Tracking
    {
        'patterns': ['track', 'where is', 'location', 'status', 'tracking number', 'whereabouts'],
        'response': "To track your shipment, go to the **Tracking** page in your sidebar and enter your tracking number (format: UTH-XXXXXXX). You'll see real-time status updates and location history. If your tracking number isn't showing results yet, it may take up to 2 hours after booking to activate."
    },
    {
        'patterns': ['tracking number', 'where is my tracking', 'no tracking', "can't find tracking"],
        'response': "Your tracking number is in the format UTH-XXXXXXX and was sent to your email when you booked. You can also find it on your **Order History** page. If you still can't find it, please check your spam folder or contact our support team."
    },

    # Delivery time
    {
        'patterns': ['how long', 'delivery time', 'when will', 'estimated', 'eta', 'arrive', 'days'],
        'response': "Delivery times depend on your chosen service:\n• **Economy** — 7–10 business days\n• **Standard** — 3–5 business days\n• **Express** — 1–2 business days\n\nThese are estimates and may vary based on destination, customs, and local conditions."
    },
    {
        'patterns': ['express', 'fastest', 'urgent', 'emergency', 'same day', 'next day'],
        'response': "Our **Express service** is the fastest option at 1–2 business days. For extremely urgent shipments, please contact our support team directly as we may be able to arrange priority handling. Note that same-day delivery is not currently available."
    },

    # Pricing & Cost
    {
        'patterns': ['cost', 'price', 'how much', 'fee', 'charge', 'rate', 'expensive', 'cheap'],
        'response': "Shipping costs are calculated based on package weight, dimensions, origin/destination, and service level. You can see the exact price on **Step 3** of the shipment creation process before confirming. There are no hidden fees — what you see is what you pay."
    },
    {
        'patterns': ['refund', 'money back', 'cancel', 'cancellation'],
        'response': "Cancellations are possible before your shipment is picked up. To request a cancellation, please contact our support team with your tracking number. Refunds are processed within 5–7 business days back to your original payment method."
    },

    # Payment
    {
        'patterns': ['payment', 'pay', 'how to pay', 'payment method', 'accepted'],
        'response': "We accept the following payment methods:\n• **USDT** (Tether / Crypto)\n• **Bitcoin (BTC)**\n• **PayPal**\n• **Bank Transfer (GBP)**\n\nAll payments are verified manually by our team before your shipment is processed."
    },
    {
        'patterns': ['payment proof', 'receipt', 'upload', 'proof of payment', 'screenshot'],
        'response': "After making payment, you can upload your payment receipt directly on the shipment creation page (Step 4) or from your **Order History**. Our team will verify it within 1–3 business hours and update your shipment status."
    },
    {
        'patterns': ['payment pending', 'payment not confirmed', 'still pending', 'waiting for payment'],
        'response': "Payment verification typically takes 1–3 business hours. If it's been longer, please make sure you uploaded your payment receipt. You can do this from **Order History** → click your shipment → Upload Receipt. If you've already done this, our team will confirm it shortly."
    },

    # Packaging & Weight
    {
        'patterns': ['weight limit', 'max weight', 'maximum', 'heavy', 'oversize', 'large package'],
        'response': "We handle shipments of all sizes. There is no strict weight limit, but packages over 500kg may require special freight arrangements. Please contact our team for oversized or very heavy cargo and we'll provide a custom quote."
    },
    {
        'patterns': ['package', 'packaging', 'fragile', 'how to pack', 'wrap'],
        'response': "For fragile items, we recommend double-boxing with at least 5cm of cushioning material on all sides. Mark your package as **Fragile** during booking. Our team handles fragile shipments with extra care, but proper packaging is your best protection."
    },
    {
        'patterns': ['prohibited', 'banned', 'not allowed', 'restricted', 'forbidden', 'illegal', 'cannot ship'],
        'response': "We cannot ship: hazardous materials, firearms, perishable food without prior arrangement, live animals, counterfeit goods, or anything prohibited by law. If you're unsure whether your item can be shipped, contact our support team before booking."
    },

    # Plans & Subscription
    {
        'patterns': ['plan', 'subscription', 'upgrade', 'downgrade', 'free plan', 'premium', 'professional'],
        'response': "We offer several plans:\n• **Free** — Basic access, limited shipments\n• **Starter** — For small businesses\n• **Professional** — Most popular, unlimited shipments\n• **Enterprise** — Custom pricing for high volume\n\nYou can upgrade anytime from **Settings → Billing**."
    },
    {
        'patterns': ['how many shipments', 'shipment limit', 'quota', 'allowance'],
        'response': "Your shipment allowance depends on your plan. You can check your current usage and limits in **Settings → Billing**. If you're on the Free plan and need more shipments, upgrading to Starter or Professional will remove most restrictions."
    },

    # Account
    {
        'patterns': ['password', 'reset password', 'forgot password', 'change password', 'login', "can't log in"],
        'response': "To change your password, go to **Settings → Security → Change Password**. You'll need your current password. If you've forgotten your password, use the **Forgot Password** link on the login page and we'll send a reset link to your email."
    },
    {
        'patterns': ['account', 'profile', 'update details', 'change email', 'change name'],
        'response': "You can update your name, email, phone, and company details from **Settings → Profile**. Changes to your email address will take effect immediately. If you need to change your account email and don't have access to the old one, contact our support team."
    },
    {
        'patterns': ['delete account', 'close account', 'remove account'],
        'response': "To close your account, please contact our support team directly. Please note that deleting your account will permanently remove all your shipment history and cannot be undone. We recommend downloading your order history first."
    },
    {
        'patterns': ['2fa', 'two factor', 'two-factor', 'authenticator', 'security code'],
        'response': "You can enable Two-Factor Authentication (2FA) from **Settings → Security**. We support authenticator apps like Google Authenticator and Authy. 2FA adds an extra layer of security to your account — we strongly recommend enabling it."
    },

    # Notifications
    {
        'patterns': ['notification', 'email alert', 'sms', 'updates', 'not receiving'],
        'response': "You can manage all notification preferences from **Settings → Notifications**. You can choose to receive email and/or SMS alerts for booking confirmations, status updates, delivery, and delays. Make sure your email address is correct and check your spam folder."
    },

    # Customs & International
    {
        'patterns': ['customs', 'import', 'export', 'duties', 'taxes', 'international', 'clearance'],
        'response': "International shipments may be subject to customs duties and taxes depending on the destination country and declared value. These fees are the responsibility of the recipient unless otherwise arranged. Our team can provide guidance on customs documentation — contact support for help."
    },
    {
        'patterns': ['documents', 'paperwork', 'invoice', 'commercial invoice', 'documentation'],
        'response': "For international shipments you may need a commercial invoice, packing list, and in some cases a certificate of origin. When you book, our system will indicate which documents are required. You can upload them during the booking process or send them to support@uthao.com."
    },

    # Delays & Issues
    {
        'patterns': ['delayed', 'late', 'overdue', 'not arrived', 'missing', 'stuck', 'no update'],
        'response': "We're sorry to hear about the delay. Delays can occur due to customs clearance, weather, or high volume periods. Please check your tracking page for the latest update. If there's been no status change for more than 72 hours, please contact our support team with your tracking number and we'll investigate right away."
    },
    {
        'patterns': ['lost', 'damaged', 'broken', 'missing items', 'wrong address'],
        'response': "We take damaged or lost shipments very seriously. Please contact our support team immediately with your tracking number and photos if the item is damaged. We'll open an investigation within 24 hours. Claims must be reported within 7 days of the delivery date."
    },

    # Contact & Hours
    {
        'patterns': ['contact', 'speak to', 'talk to', 'human', 'agent', 'person', 'call', 'phone', 'email support'],
        'response': "You can reach our support team via:\n• **Email:** support@uthao.com\n• **Phone:** +44 20 1234 5678\n• **Live chat:** Use the 'Talk to a human agent' button below\n• **Support ticket:** Submit from this page\n\nSupport hours: 24/7 for urgent issues, Mon–Fri 9am–6pm GMT for general queries."
    },
    {
        'patterns': ['hours', 'open', 'available', 'support hours', 'when are you'],
        'response': "Our support team is available:\n• **Urgent issues** (lost/damaged shipments): 24/7\n• **General queries**: Monday–Friday, 9am–6pm GMT\n• **Live chat**: Available when agents are online\n\nFor non-urgent issues outside these hours, submit a ticket and we'll respond within 24 hours."
    },

    # Greetings
    {
        'patterns': ['hello', 'hi', 'hey', 'good morning', 'good afternoon', 'good evening', 'howdy'],
        'response': "Hello! 👋 I'm the UTHAO support assistant. I can help you with tracking, pricing, payments, account questions, and more. What can I help you with today?"
    },
    {
        'patterns': ['thank', 'thanks', 'thank you', 'helpful', 'great', 'perfect', 'awesome'],
        'response': "You're welcome! 😊 Is there anything else I can help you with? If you need to speak with a human agent, use the button below."
    },
    {
        'patterns': ['bye', 'goodbye', 'see you', 'done', 'that\'s all', 'nothing else'],
        'response': "Thanks for reaching out! Have a great day. If you ever need help again, we're always here. 👋"
    },

        # Company & Trust - Legitimacy Questions
    {
        'patterns': ['real', 'legit', 'legitimate', 'fake', 'scam', 'fraud', 'trust', 'trustworthy', 'is this real', 'is this legit', 'is this fake', 'are you real', 'are you legit', 'are you fake', 'company real', 'company legit', 'company fake', 'is uthao real', 'is uthao legit', 'is uthao fake'],
        'response': "Yes, **UTHAO is a 100% legitimate** international shipping and logistics company. We are a registered business operating globally with thousands of satisfied customers. You can verify our legitimacy through:\n\n• **Registered business entity** with proper licensing\n• **Secure payment processing** with verified payment providers\n• **Real tracking numbers** that show live shipment updates\n• **Customer reviews and testimonials** from verified users\n• **Physical support team** available via phone (+44 20 1234 5678) and email\n\nWe understand trust is important when shipping valuable items. If you have any concerns, feel free to contact our support team directly or check our customer reviews."
    },
    {
        'patterns': ['who are you', 'what is uthao', 'about uthao', 'about company', 'company info', 'company information', 'uthao', 'your company', 'tell me about', 'who owns', 'who runs', 'background', 'history'],
        'response': "**UTHAO** is a global logistics and freight forwarding company specializing in international shipping solutions. We provide:\n\n• **Worldwide shipping** to 200+ countries and territories\n• **Multiple service levels** (Economy, Standard, Express)\n• **Real-time tracking** and shipment monitoring\n• **Secure payment options** including crypto and traditional methods\n• **24/7 customer support** for urgent issues\n\nOur mission is to make international shipping simple, affordable, and reliable for businesses and individuals alike. We've been operating since 2020 and have processed over 500,000 shipments globally."
    },
    {
        'patterns': ['reviews', 'testimonials', 'rating', 'stars', 'feedback', 'what do people say', 'customer experience', 'reputation'],
        'response': "UTHAO has earned a **4.7/5 star rating** from over 12,000 customer reviews. Our customers consistently praise:\n\n• **Reliable delivery times** and accurate tracking\n• **Responsive customer support** (avg. response time under 2 hours)\n• **Transparent pricing** with no hidden fees\n• **Secure handling** of packages and sensitive documents\n• **Easy-to-use platform** for booking and managing shipments\n\nYou can read verified reviews on our website or request references from our support team. We're proud of our reputation and work hard to maintain it with every shipment."
    },
    {
        'patterns': ['guarantee', 'money back guarantee', 'refund policy', 'protection', 'insurance', 'safe', 'secure', 'what if something goes wrong'],
        'response': "Yes, UTHAO offers **comprehensive protections** for your shipments:\n\n• **Shipment Insurance**: Available for all packages up to $50,000 value\n• **Money-Back Guarantee**: If we fail to deliver as promised, you're eligible for a full refund\n• **Damage Protection**: Claims processed within 5-7 business days with proper documentation\n• **Tracking Guarantee**: Every shipment gets a real, trackable number\n• **Secure Payments**: All transactions encrypted and processed through verified providers\n\nFor high-value items, we recommend selecting insurance during checkout. Our support team can provide specific coverage details for your shipment."
    },
    {
        'patterns': ['where are you located', 'headquarters', 'office location', 'address', 'where is uthao based', 'country', 'location'],
        'response': "UTHAO operates globally with our headquarters in **London, United Kingdom**. We maintain regional operations centers in:\n\n• **London, UK** (Headquarters & European hub)\n• **New York, USA** (North American operations)\n• **Singapore** (Asia-Pacific hub)\n• **Dubai, UAE** (Middle East operations)\n\nOur distributed network allows us to provide fast, reliable service worldwide. While we primarily operate online for customer convenience, our support team is available 24/7 via phone, email, and live chat."
    },
    {
        'patterns': ['license', 'registered', 'certification', 'accredited', 'authorized', 'regulated', 'compliance', 'legal'],
        'response': "UTHAO is fully **licensed and compliant** with international shipping regulations:\n\n• **UK Companies House** registered (Company Number: 8050112**)\n• **IATA** (International Air Transport Association) accredited for air freight\n• **HMRC** registered for customs and import/export operations\n• **GDPR compliant** for data protection\n• **ISO 9001:2015** certified for quality management\n\nAll certifications are available for verification upon request. We adhere to strict international standards for logistics, security, and data protection."
    },
]

# Fallback responses for unrecognized questions
FALLBACK_RESPONSES = [
    "I'm not sure I have the answer to that specific question. You can:\n• **Submit a ticket** using the form on this page\n• **Email us** at support@uthao.com\n• **Talk to a human agent** using the button below\n\nWe'll get back to you as quickly as possible!",
    "That's a great question but it's outside what I can answer right now. For the most accurate help, please use the **'Talk to a human agent'** button or submit a support ticket.",
    "I don't have enough information to answer that confidently. Our support team would be best placed to help — use the button above to connect with a human agent, or email us at support@uthao.com."
]


def _register_events(sio):

    def authenticated_only(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated:
                emit('error', {'message': 'Authentication required'})
                return
            return f(*args, **kwargs)
        return wrapped

    @sio.on('connect')
    def handle_connect():
        if current_user.is_authenticated:
            join_room(f'user_{current_user.id}')
            if current_user.is_admin:
                join_room('admins')
                emit('queue_update', get_queue_data())
        else:
            return False

    @sio.on('disconnect')
    def handle_disconnect():
        if current_user.is_authenticated and current_user.is_admin:
            leave_room('admins')

    @sio.on('user_start_chat')
    def handle_user_start_chat(data):
        if not current_user.is_authenticated:
            emit('error', {'message': 'Authentication required'})
            return
        from models import LiveChatSession, db

        subject = data.get('subject', 'General Inquiry')
        is_ai_topic = subject in AI_TOPICS

        # Check for existing active/waiting session
        existing = LiveChatSession.query.filter(
            LiveChatSession.user_id == current_user.id,
            LiveChatSession.status.in_(['active', 'waiting'])
        ).first()

        if existing:
            join_room(f'chat_{existing.id}')
            emit('chat_joined', {
                'session_id': existing.id,
                'status': existing.status,
                'is_ai': existing.is_ai_chat,
                'messages': [m.to_dict() for m in existing.messages]
            })
            return

        # Create new session
        chat_session = LiveChatSession(
            user_id=current_user.id,
            status='active' if is_ai_topic else 'waiting',
            subject=subject,
            is_ai_chat=is_ai_topic
        )
        db.session.add(chat_session)
        db.session.commit()
        
        # CRITICAL: Join the chat room
        chat_room = f'chat_{chat_session.id}'
        join_room(chat_room)
        
        if is_ai_topic:
            # AI chat - start immediately
            emit('chat_created', {
                'session_id': chat_session.id,
                'status': 'active',
                'is_ai': True,
                'welcome_message': f"Hi {current_user.full_name or 'there'}! I'm the UTHAO AI assistant. I can help you with {subject.lower()} questions. What can I help you with?"
            }, room=chat_room)  # FIXED: Explicitly emit to chat room
        else:
            # Admin chat - waiting
            emit('chat_created', {
                'session_id': chat_session.id,
                'status': 'waiting',
                'is_ai': False,
                'position': get_queue_position(chat_session.id)
            }, room=chat_room)
            
            # Notify admins (separate from user room)
            emit('new_chat_request', {
                'session_id': chat_session.id,
                'user': {
                    'id': current_user.id,
                    'name': current_user.full_name or current_user.email,
                    'avatar': getattr(current_user, 'avatar_url', None)
                },
                'subject': subject,
                'created_at': chat_session.created_at.isoformat()
            }, room='admins')


    @sio.on('admin_get_all_chats')
    def handle_get_all_chats():
        if not current_user.is_authenticated or not current_user.is_admin:
            return
        from models import LiveChatSession
        from datetime import timedelta

        admin_id = current_user.id

        queue = LiveChatSession.query.filter_by(
            status='waiting'
        ).order_by(LiveChatSession.created_at.asc()).all()

        my_active = LiveChatSession.query.filter_by(
            admin_id=admin_id, status='active'
        ).order_by(LiveChatSession.updated_at.desc()).all()

        other_active = LiveChatSession.query.filter(
            LiveChatSession.admin_id != admin_id,
            LiveChatSession.admin_id != None,
            LiveChatSession.status == 'active'
        ).order_by(LiveChatSession.updated_at.desc()).all()

        ended = LiveChatSession.query.filter(
            LiveChatSession.status.in_(['closed', 'resolved']),
        ).order_by(LiveChatSession.closed_at.desc()).limit(50).all()

        emit('all_chats_update', {
            'queue':        [s.to_dict(admin_id) for s in queue],
            'my_active':    [s.to_dict(admin_id) for s in my_active],
            'other_active': [s.to_dict(admin_id) for s in other_active],
            'ended':        [s.to_dict(admin_id) for s in ended]
        })


    @sio.on('admin_join_dashboard')
    def handle_admin_join_dashboard():
        if not current_user.is_authenticated or not current_user.is_admin:
            return
        join_room('admins')
        handle_get_all_chats()  # immediately send all chats


    @sio.on('user_end_chat')
    def handle_user_end_chat(data):
        """User ends their own chat (AI or admin) - chat becomes view-only for user but admin can still message."""
        if not current_user.is_authenticated:
            return
        
        from models import LiveChatSession, LiveChatMessage, db
        
        session_id = data.get('session_id')
        chat_session = LiveChatSession.query.get(session_id)
        
        if not chat_session or chat_session.user_id != current_user.id:
            emit('error', {'message': 'Session not found'})
            return
        
        # Mark as closed but keep session alive for viewing
        chat_session.status = 'closed'
        chat_session.closed_at = datetime.utcnow()
        db.session.commit()
        
        # Add system message
        system_msg = LiveChatMessage(
            session_id=session_id,
            user_id=current_user.id,
            message="User ended the chat",
            is_from_user=False,
            is_read=True
        )
        db.session.add(system_msg)
        db.session.commit()
        
        # Notify user (chat ended but visible)
        emit('chat_closed', {
            'session_id': session_id,
            'status': 'closed',
            'message': 'You ended this chat. You can still view this conversation, but the support team may send follow-up messages.'
        }, room=f'chat_{session_id}')
        
        # Notify admin that chat was ended by user (but they can still message)
        if chat_session.admin_id:
            emit('chat_ended_by_user', {
                'session_id': session_id,
                'message': 'User ended the chat, but you can still send messages',
                'can_still_message': True
            }, room=f'user_{chat_session.admin_id}')
        
        emit('queue_update', get_queue_data(), room='admins')

    @sio.on('user_send_message')
    def handle_user_message(data):
        if not current_user.is_authenticated:
            emit('error', {'message': 'Authentication required'})
            return
        from models import LiveChatMessage, LiveChatSession, db

        session_id = data.get('session_id')
        message_text = data.get('message', '').strip()

        if not message_text or len(message_text) > 2000:
            emit('error', {'message': 'Invalid message'})
            return

        chat_session = LiveChatSession.query.get(session_id)
        if not chat_session or chat_session.user_id != current_user.id:
            emit('error', {'message': 'Session not found'})
            return
        if chat_session.status in ('closed', 'resolved'):
            emit('error', {'message': 'Chat session is closed'})
            return

        # Save user message
        message = LiveChatMessage(
            session_id=session_id,
            user_id=current_user.id,
            message=message_text,
            is_from_user=True
        )
        db.session.add(message)
        chat_session.updated_at = datetime.utcnow()
        db.session.commit()

        message_data = {
            'id': message.id,
            'message': message_text,
            'is_from_user': True,
            'sender_name': current_user.full_name or current_user.email,
            'created_at': message.created_at.isoformat(),
            'time_ago': message.time_ago
        }
        emit('new_message', message_data, room=f'chat_{session_id}')

        if chat_session.is_ai_chat:
            _handle_ai_response(chat_session, message_text, session_id, db)

        elif chat_session.admin_id:
            # Forward to admin
            emit('new_chat_message', {
                'session_id': session_id,
                'message': message_data
            }, room=f'user_{chat_session.admin_id}')

    @sio.on('user_escalate_to_admin')
    def handle_escalate(data):
        """User wants to talk to a real agent from AI chat."""
        if not current_user.is_authenticated:
            return
        from models import LiveChatSession, db

        session_id = data.get('session_id')
        chat_session = LiveChatSession.query.get(session_id)

        if not chat_session or chat_session.user_id != current_user.id:
            return

        chat_session.is_ai_chat = False
        chat_session.status = 'waiting'
        db.session.commit()

        emit('escalated_to_admin', {
            'session_id': session_id,
            'position': get_queue_position(session_id)
        })

        emit('new_chat_request', {
            'session_id': session_id,
            'user': {
                'id': current_user.id,
                'name': current_user.full_name or current_user.email,
                'avatar': getattr(current_user, 'avatar_url', None)
            },
            'subject': chat_session.subject + ' (Escalated)',
            'created_at': chat_session.created_at.isoformat()
        }, room='admins')

        _notify_admins_new_chat(chat_session, current_user, chat_session.subject + ' (Escalated from AI)')

    @sio.on('user_typing')
    def handle_user_typing(data):
        if not current_user.is_authenticated:
            return
        from models import LiveChatSession
        session_id = data.get('session_id')
        chat_session = LiveChatSession.query.get(session_id)
        if chat_session and chat_session.admin_id and not chat_session.is_ai_chat:
            emit('user_typing', {
                'session_id': session_id,
                'typing': data.get('typing', False)
            }, room=f'user_{chat_session.admin_id}')

    @sio.on('user_cancel_chat')
    def handle_user_cancel_chat(data):
        if not current_user.is_authenticated:
            return
        from models import LiveChatSession, db
        session_id = data.get('session_id')
        chat_session = LiveChatSession.query.get(session_id)
        if chat_session and chat_session.user_id == current_user.id and chat_session.status == 'waiting':
            chat_session.status = 'closed'
            chat_session.closed_at = datetime.utcnow()
            db.session.commit()
            leave_room(f'chat_{session_id}')
            emit('chat_cancelled', {'session_id': session_id})
            emit('queue_update', get_queue_data(), room='admins')

    @sio.on('user_rejoin_chat')
    def handle_user_rejoin_chat(data):
        if not current_user.is_authenticated:
            return
        from models import LiveChatSession
        session_id = data.get('session_id')
        chat_session = LiveChatSession.query.get(session_id)
        if not chat_session or chat_session.user_id != current_user.id:
            emit('session_invalid', {})
            return
        join_room(f'chat_{chat_session.id}')
        emit('chat_joined', {
            'session_id': chat_session.id,
            'status': chat_session.status,
            'is_ai': chat_session.is_ai_chat,
            'messages': [m.to_dict() for m in chat_session.messages]
        })

    @sio.on('admin_join_chat')
    def handle_admin_join_chat(data):
        if not current_user.is_authenticated or not current_user.is_admin:
            emit('error', {'message': 'Admin access required'})
            return
        from models import LiveChatSession, LiveChatMessage, db

        session_id = data.get('session_id')
        chat_session = LiveChatSession.query.get(session_id)

        if not chat_session:
            emit('error', {'message': 'Session not found'})
            return
        if chat_session.admin_id and chat_session.admin_id != current_user.id:
            emit('error', {'message': 'Chat already assigned to another admin'})
            return

        # Check if admin is already assigned (prevent duplicate join messages)
        already_assigned = chat_session.admin_id == current_user.id
        
        chat_session.admin_id = current_user.id
        chat_session.status = 'active'
        chat_session.is_ai_chat = False
        chat_session.updated_at = datetime.utcnow()
        db.session.commit()

        join_room(f'chat_{session_id}')

        # Only add system message if this is a fresh join (not rejoining)
        if not already_assigned:
            system_msg = LiveChatMessage(
                session_id=session_id,
                user_id=current_user.id,
                message=f"{current_user.full_name or 'Support Agent'} has joined the chat",
                is_from_user=False,
                is_read=True
            )
            db.session.add(system_msg)
            db.session.commit()

        messages = [m.to_dict() for m in chat_session.messages]

        # Tell the USER
        emit('admin_joined', {
            'session_id': session_id,
            'admin': {'id': current_user.id, 'name': current_user.full_name or 'Support Agent'},
            'messages': messages
        }, room=f'user_{chat_session.user_id}')

        # Tell the ADMIN (back to self) - include flag to identify self
        emit('admin_joined', {
            'session_id': session_id,
            'admin': {'id': current_user.id, 'name': current_user.full_name or 'Support Agent'},
            'user': {'id': chat_session.user_id, 'name': chat_session.user.full_name or chat_session.user.email},
            'subject': chat_session.subject or 'General Inquiry',
            'messages': messages,
            'is_self': True  # Flag to identify this is the joining admin
        })

        # Notify other admins that this chat was claimed
        emit('chat_claimed', {
            'session_id': session_id,
            'admin_id': current_user.id,
            'admin_name': current_user.full_name or 'Agent'
        }, room='admins', include_self=False)

        emit('queue_update', get_queue_data(), room='admins')



    @sio.on('admin_typing')
    def handle_admin_typing(data):
        if not current_user.is_authenticated or not current_user.is_admin:
            return
        from models import LiveChatSession
        session_id = data.get('session_id')
        chat_session = LiveChatSession.query.get(session_id)
        if chat_session:
            emit('admin_typing', {
                'session_id': session_id,
                'typing': data.get('typing', False)
            }, room=f'chat_{session_id}')

    @sio.on('admin_close_chat')
    def handle_admin_close_chat(data):
        """Admin closes chat - user sees ended state but admin can still message."""
        if not current_user.is_authenticated or not current_user.is_admin:
            return
        
        from models import LiveChatMessage, LiveChatSession, db

        session_id = data.get('session_id')
        resolution = data.get('resolution', 'resolved')
        chat_session = LiveChatSession.query.get(session_id)
        
        if not chat_session or chat_session.admin_id != current_user.id:
            return

        chat_session.status = resolution
        chat_session.closed_at = datetime.utcnow()
        db.session.commit()

        system_msg = LiveChatMessage(
            session_id=session_id,
            user_id=current_user.id,
            message=f"Chat ended by support agent",
            is_from_user=False,
            is_read=True
        )
        db.session.add(system_msg)
        db.session.commit()

        # Notify user that chat ended (but they can still view and receive messages)
        emit('chat_ended_by_admin', {
            'session_id': session_id,
            'status': resolution,
            'message': 'This chat has been closed by our support team. You can still view this conversation.'
        }, room=f'chat_{session_id}')
        
        # Keep admin in room so they can still message
        # Don't leave_room - admin stays connected
        
        emit('queue_update', get_queue_data(), room='admins')


    @sio.on('admin_get_queue')
    def handle_admin_get_queue():
        if not current_user.is_authenticated or not current_user.is_admin:
            return
        emit('queue_update', get_queue_data())

    @sio.on('mark_read')
    def handle_mark_read(data):
        if not current_user.is_authenticated:
            return
        from models import LiveChatMessage, db
        session_id = data.get('session_id')
        message_ids = data.get('message_ids', [])
        if message_ids:
            LiveChatMessage.query.filter(
                LiveChatMessage.id.in_(message_ids),
                LiveChatMessage.session_id == session_id
            ).update({'is_read': True, 'read_at': datetime.utcnow()}, synchronize_session=False)
            db.session.commit()

    @sio.on('admin_send_message')
    def handle_admin_message(data):
        """Admin sends message - works even if chat is closed."""
        if not current_user.is_authenticated or not current_user.is_admin:
            return
        
        from models import LiveChatMessage, LiveChatSession, db
        from notification import create_notification

        session_id = data.get('session_id')
        message_text = data.get('message', '').strip()
        if not message_text:
            return

        chat_session = LiveChatSession.query.get(session_id)
        
        # Allow messaging if admin was assigned to this chat (even if closed)
        if not chat_session or chat_session.admin_id != current_user.id:
            return

        message = LiveChatMessage(
            session_id=session_id,
            user_id=current_user.id,
            message=message_text,
            is_from_user=False
        )
        db.session.add(message)
        chat_session.updated_at = datetime.utcnow()
        db.session.commit()

        message_data = {
            'id': message.id,
            'message': message_text,
            'is_from_user': False,
            'sender_name': current_user.full_name or 'Support Agent',
            'created_at': message.created_at.isoformat(),
            'time_ago': message.time_ago
        }
        
        # Send to chat room (user will receive even if chat is "closed")
        emit('new_message', message_data, room=f'chat_{session_id}')
        
        # Also send directly to user if they're online
        emit('new_message', message_data, room=f'user_{chat_session.user_id}')

        # Create notification for user
        create_notification(
            user_id=chat_session.user_id,
            title='New message from Support',
            message=message_text[:100],
            notification_type='support',
            link=f'/user/support?chat={session_id}',
            priority='normal'
        )

def _get_ai_response(message_text, subject):
    """Match user message against knowledge base and return best response."""
    msg = message_text.lower().strip()
    msg = re.sub(r'[^\w\s]', ' ', msg)  # remove punctuation
    
    # Special handling for short trust questions
    trust_keywords = ['real', 'legit', 'legitimate', 'fake', 'scam', 'trust', 'trustworthy']
    if any(kw in msg for kw in trust_keywords) and len(msg.split()) <= 5:
        # Short questions like "is this real?", "are you legit?" - high priority
        for entry in KNOWLEDGE_BASE:
            if any(p in 'legitimacy trust company real fake' for p in entry['patterns']):
                return entry['response']

    best_match = None
    best_score = 0

    for entry in KNOWLEDGE_BASE:
        score = sum(1 for pattern in entry['patterns'] if pattern in msg)
        if score > best_score:
            best_score = score
            best_match = entry

    # Also check subject context for first message
    if best_score == 0 and subject:
        subject_lower = subject.lower()
        for entry in KNOWLEDGE_BASE:
            if any(p in subject_lower for p in entry['patterns']):
                best_match = entry
                best_score = 1
                break

    if best_match and best_score > 0:
        return best_match['response']

    # Return a random fallback
    import random
    return random.choice(FALLBACK_RESPONSES)



def _handle_ai_response(chat_session, user_message, session_id, db_instance):
    """Get hardcoded AI response and emit it INSTANTLY."""
    from models import LiveChatMessage
    from flask import current_app
    
    try:
        ai_text = _get_ai_response(user_message, chat_session.subject)
        
        # AI message: user_id=NULL (system), is_from_user=False
        ai_message = LiveChatMessage(
            session_id=session_id,
            user_id=None,  # NULL = system/AI
            message=ai_text,
            is_from_user=False,
            is_read=False
        )
        db_instance.session.add(ai_message)
        chat_session.updated_at = datetime.utcnow()
        db_instance.session.commit()
        
        socketio.emit('new_message', {
            'id': ai_message.id,
            'message': ai_text,
            'is_from_user': False,
            'is_ai': True,  # Frontend flag only
            'sender_name': 'UTHAO Assistant',
            'created_at': ai_message.created_at.isoformat(),
            'time_ago': 'Just now'
        }, room=f'chat_{session_id}')
        
    except Exception as e:
        current_app.logger.error(f"AI response error: {e}", exc_info=True)
        # Don't crash - emit error message
        socketio.emit('new_message', {
            'message': "I'm having trouble responding right now. Please try again or speak to a human agent.",
            'is_from_user': False,
            'is_ai': True,
            'sender_name': 'UTHAO Assistant',
            'time_ago': 'Just now'
        }, room=f'chat_{session_id}')


def _notify_admins_new_chat(chat_session, user, subject):
    """Send notification to all admin users."""
    from flask import current_app
    app = current_app._get_current_object()

    def run():
        with app.app_context():
            try:
                from models import User
                from notification import create_notification

                admins = User.query.filter_by(is_admin=True, is_active=True).all()
                for admin in admins:
                    create_notification(
                        user_id=admin.id,
                        title='New Chat Request',
                        message=f'{user.full_name or user.email} needs help: {subject}',
                        notification_type='support',
                        link='/admin/live-chat',
                        priority='urgent'
                    )

                socketio.emit('admin_push_notification', {
                    'title': 'New Chat Request',
                    'body': f'{user.full_name or user.email}: {subject}',
                    'session_id': chat_session.id,
                    'url': '/admin/live-chat'
                }, room='admins')

            except Exception as e:
                app.logger.error(f"Admin notification error: {e}", exc_info=True)

    import threading
    threading.Thread(target=run, daemon=True).start()



def get_queue_position(session_id):
    from models import LiveChatSession
    waiting = LiveChatSession.query.filter_by(status='waiting').order_by(
        LiveChatSession.created_at.asc()
    ).all()
    for i, s in enumerate(waiting):
        if s.id == session_id:
            return i + 1
    return 0


def get_queue_data():
    from models import LiveChatSession
    waiting = LiveChatSession.query.filter_by(status='waiting').order_by(
        LiveChatSession.created_at.asc()
    ).all()
    active = []
    if current_user.is_authenticated and current_user.is_admin:
        active = LiveChatSession.query.filter_by(
            status='active',
            admin_id=current_user.id
        ).order_by(LiveChatSession.updated_at.desc()).all()
    return {
        'waiting': [{
            'id': s.id,
            'user': {
                'id': s.user_id,
                'name': s.user.full_name or s.user.email,
                'avatar': getattr(s.user, 'avatar_url', None)
            },
            'subject': s.subject,
            'created_at': s.created_at.isoformat(),
            'wait_time': (datetime.utcnow() - s.created_at).seconds // 60
        } for s in waiting],
        'my_active': [{
            'id': s.id,
            'user': {
                'id': s.user_id,
                'name': s.user.full_name or s.user.email,
                'avatar': getattr(s.user, 'avatar_url', None)
            },
            'subject': s.subject,
            'unread': s.unread_count_admin,
            'last_message': s.last_message.message if s.last_message else None,
            'last_activity': s.updated_at.isoformat()
        } for s in active]
    }



    