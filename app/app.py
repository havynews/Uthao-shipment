# app.py
from flask import Flask, request, render_template, flash, redirect, make_response
from config import Config
from flask_socketio import SocketIO
import os
from models import User  
from extensions import db, mail, login_manager, migrate
from socket_events import init_socket_events
from werkzeug.security import generate_password_hash
from datetime import datetime
from sqlalchemy.exc import OperationalError
from sqlalchemy import text
import logging

socketio = SocketIO(cors_allowed_origins="*", async_mode='gevent', logger=True, engineio_logger=True)
logger = logging.getLogger(__name__)

# HTML template for offline page (inline to avoid template rendering issues)
OFFLINE_HTML = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Connection Issue - UTHAO Logistics</title>
    <link href="https://fonts.googleapis.com/css2?family=Syne:wght@400;600;700;800&family=DM+Mono:wght@300;400;500&display=swap" rel="stylesheet">
    <style>
        *, *::before, *::after { margin: 0; padding: 0; box-sizing: border-box; }

        :root {
            --orange: #FF5C1A;
            --orange-dim: rgba(255, 92, 26, 0.18);
            --white: #FFFFFF;
            --gray-100: rgba(255,255,255,0.08);
            --gray-200: rgba(255,255,255,0.13);
            --gray-text: rgba(255,255,255,0.55);
            --error-red: #FF3B3B;
        }

        body {
            font-family: 'Syne', sans-serif;
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
            overflow: hidden;
            background: #0a0a0f;
            color: var(--white);
        }

        /* ── Background ── */
        .bg {
            position: fixed;
            inset: 0;
            z-index: 0;
            /* Primary: real photo */
            background-image: url('https://picsum.photos/id/1040/1800/1000');
            background-size: cover;
            background-position: center 40%;
            filter: brightness(0.35) saturate(0.7);
            transform: scale(1.06);
            animation: bgBreath 14s ease-in-out infinite alternate;
        }

        /* Fallback dark geometric pattern if image fails */
        .bg::after {
            content: '';
            position: absolute;
            inset: 0;
            background:
                repeating-linear-gradient(
                    0deg,
                    transparent,
                    transparent 59px,
                    rgba(255,255,255,0.018) 60px
                ),
                repeating-linear-gradient(
                    90deg,
                    transparent,
                    transparent 59px,
                    rgba(255,255,255,0.018) 60px
                ),
                linear-gradient(135deg, #0d0d18 0%, #160a0a 50%, #0a0d18 100%);
            z-index: 1;
            /* Hidden when image loads — acts as fallback texture underneath overlay */
        }

        @keyframes bgBreath {
            from { transform: scale(1.06); }
            to   { transform: scale(1.13); }
        }

        /* dark vignette + tint overlay */
        .bg-overlay {
            position: fixed;
            inset: 0;
            z-index: 2;
            background:
                radial-gradient(ellipse 80% 80% at 50% 50%, rgba(0,0,0,0.35) 0%, rgba(0,0,0,0.82) 100%),
                linear-gradient(180deg, rgba(10,10,15,0.55) 0%, rgba(10,10,15,0.75) 100%);
        }

        /* floating orb glows */
        .orb {
            position: fixed;
            border-radius: 50%;
            filter: blur(100px);
            pointer-events: none;
            z-index: 3;
            animation: orbDrift 18s ease-in-out infinite alternate;
        }
        .orb-1 {
            width: 500px; height: 500px;
            background: rgba(255, 92, 26, 0.10);
            top: -150px; right: -100px;
            animation-delay: 0s;
        }
        .orb-2 {
            width: 360px; height: 360px;
            background: rgba(60, 80, 200, 0.08);
            bottom: -100px; left: -80px;
            animation-delay: -6s;
        }
        @keyframes orbDrift {
            from { transform: translate(0, 0) scale(1); }
            to   { transform: translate(30px, 20px) scale(1.1); }
        }

        /* ── Card ── */
        .card {
            position: relative;
            z-index: 10;
            width: 100%;
            max-width: 640px;
            background: rgba(12, 12, 20, 0.78);
            backdrop-filter: blur(32px) saturate(1.5);
            -webkit-backdrop-filter: blur(32px) saturate(1.5);
            border: 1px solid rgba(255,255,255,0.09);
            border-radius: 28px;
            overflow: hidden;
            box-shadow:
                0 0 0 1px rgba(255,255,255,0.04) inset,
                0 50px 100px rgba(0,0,0,0.7),
                0 0 80px rgba(255, 92, 26, 0.07);
            animation: cardIn 0.9s cubic-bezier(0.16, 1, 0.3, 1) both;
            display: grid;
            grid-template-columns: 1fr 1fr;
        }

        /* left panel */
        .card-left {
            padding: 40px 36px 40px 40px;
            border-right: 1px solid rgba(255,255,255,0.07);
            display: flex;
            flex-direction: column;
            justify-content: space-between;
        }

        /* right panel */
        .card-right {
            padding: 40px 40px 40px 36px;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
        }

        /* accent stripe at top of right panel */
        .card-right::before {
            content: '';
            position: absolute;
            top: 0; right: 0;
            width: 50%;
            height: 2px;
            background: linear-gradient(90deg, transparent, var(--orange) 60%, transparent);
        }

        @keyframes cardIn {
            from { opacity: 0; transform: translateY(28px) scale(0.97); }
            to   { opacity: 1; transform: translateY(0) scale(1); }
        }

        /* ── Signal icon ── */
        .icon-wrap {
            position: relative;
            width: 64px;
            height: 64px;
            margin: 0 auto 24px;
            animation: cardIn 0.8s 0.1s cubic-bezier(0.16, 1, 0.3, 1) both;
        }

        .icon-bg {
            position: absolute;
            inset: 0;
            background: var(--orange-dim);
            border-radius: 18px;
            border: 1px solid rgba(255, 92, 26, 0.25);
        }

        .icon-pulse {
            position: absolute;
            inset: -8px;
            border-radius: 26px;
            border: 1.5px solid rgba(255, 92, 26, 0.3);
            animation: ringPulse 2.4s ease-out infinite;
        }
        .icon-pulse-2 {
            position: absolute;
            inset: -16px;
            border-radius: 34px;
            border: 1px solid rgba(255, 92, 26, 0.15);
            animation: ringPulse 2.4s 0.6s ease-out infinite;
        }

        @keyframes ringPulse {
            0%   { opacity: 0.8; transform: scale(0.95); }
            100% { opacity: 0;   transform: scale(1.15); }
        }

        .icon-svg {
            position: absolute;
            inset: 0;
            display: flex;
            align-items: center;
            justify-content: center;
        }

        /* animated signal bars */
        .signal-bars {
            display: flex;
            align-items: flex-end;
            gap: 3px;
            height: 24px;
        }
        .bar {
            width: 5px;
            background: var(--orange);
            border-radius: 2px;
            animation: barFade 1.6s ease-in-out infinite;
        }
        .bar:nth-child(1) { height: 8px;  animation-delay: 0s; }
        .bar:nth-child(2) { height: 14px; animation-delay: 0.2s; }
        .bar:nth-child(3) { height: 20px; animation-delay: 0.4s; }
        .bar:nth-child(4) { height: 14px; animation-delay: 0.6s; opacity: 0.3; }

        @keyframes barFade {
            0%, 100% { opacity: 1; }
            50%       { opacity: 0.2; }
        }

        /* ── Status pill ── */
        .pill {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            padding: 5px 12px;
            background: rgba(255, 59, 59, 0.12);
            border: 1px solid rgba(255, 59, 59, 0.22);
            border-radius: 100px;
            font-family: 'DM Mono', monospace;
            font-size: 10px;
            font-weight: 500;
            letter-spacing: 1.2px;
            color: var(--error-red);
            text-transform: uppercase;
            margin-bottom: 14px;
            animation: cardIn 0.8s 0.15s cubic-bezier(0.16, 1, 0.3, 1) both;
        }
        .pill-dot {
            width: 6px; height: 6px;
            background: var(--error-red);
            border-radius: 50%;
            animation: blink 1.4s ease-in-out infinite;
        }
        @keyframes blink {
            0%, 100% { opacity: 1; box-shadow: 0 0 0 0 rgba(255,59,59,0.5); }
            50%       { opacity: 0.5; box-shadow: 0 0 0 4px rgba(255,59,59,0); }
        }

        /* ── Typography ── */
        h1 {
            font-size: 26px;
            font-weight: 800;
            letter-spacing: -0.8px;
            line-height: 1.15;
            color: var(--white);
            margin-bottom: 10px;
            animation: cardIn 0.8s 0.2s cubic-bezier(0.16, 1, 0.3, 1) both;
        }
        h1 span { color: var(--orange); }

        p {
            font-family: 'DM Mono', monospace;
            font-size: 13px;
            font-weight: 300;
            line-height: 1.6;
            color: var(--gray-text);
            margin-bottom: 28px;
            animation: cardIn 0.8s 0.25s cubic-bezier(0.16, 1, 0.3, 1) both;
        }

        /* ── Divider ── */
        .divider {
            height: 1px;
            background: linear-gradient(90deg, transparent, rgba(255,255,255,0.08), transparent);
            margin-bottom: 24px;
            animation: cardIn 0.8s 0.3s both;
        }

        /* ── Buttons ── */
        .actions {
            display: flex;
            gap: 10px;
            margin-bottom: 24px;
            animation: cardIn 0.8s 0.35s cubic-bezier(0.16, 1, 0.3, 1) both;
        }

        .btn {
            flex: 1;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            gap: 7px;
            padding: 12px 18px;
            border-radius: 12px;
            font-family: 'Syne', sans-serif;
            font-size: 13px;
            font-weight: 700;
            letter-spacing: 0.3px;
            border: none;
            cursor: pointer;
            transition: transform 0.18s ease, box-shadow 0.18s ease, background 0.18s ease;
        }

        .btn-primary {
            background: var(--orange);
            color: #fff;
            box-shadow: 0 6px 24px rgba(255, 92, 26, 0.35);
        }
        .btn-primary:hover {
            transform: translateY(-2px);
            box-shadow: 0 10px 30px rgba(255, 92, 26, 0.5);
            background: #ff6e36;
        }
        .btn-primary:active { transform: translateY(0); }

        .btn-secondary {
            background: var(--gray-100);
            color: rgba(255,255,255,0.7);
            border: 1px solid rgba(255,255,255,0.08);
        }
        .btn-secondary:hover {
            background: var(--gray-200);
            color: #fff;
            transform: translateY(-1px);
        }

        /* spinning icon on retry btn */
        .spin { display: inline-block; transition: transform 0.4s ease; }
        .btn-primary:hover .spin { transform: rotate(180deg); }

        /* ── Tips ── */
        .tips {
            background: rgba(255,255,255,0.03);
            border: 1px solid rgba(255,255,255,0.07);
            border-radius: 14px;
            padding: 16px;
            animation: cardIn 0.8s 0.4s cubic-bezier(0.16, 1, 0.3, 1) both;
        }

        .tips-header {
            font-family: 'DM Mono', monospace;
            font-size: 10px;
            font-weight: 500;
            letter-spacing: 1.5px;
            text-transform: uppercase;
            color: rgba(255,255,255,0.3);
            margin-bottom: 12px;
        }

        .tip-item {
            display: flex;
            align-items: flex-start;
            gap: 10px;
            padding: 5px 0;
            font-family: 'DM Mono', monospace;
            font-size: 12px;
            font-weight: 300;
            color: rgba(255,255,255,0.5);
            line-height: 1.4;
            border-bottom: 1px solid rgba(255,255,255,0.04);
        }
        .tip-item:last-child { border-bottom: none; }

        .tip-num {
            font-weight: 500;
            color: var(--orange);
            min-width: 16px;
            font-size: 11px;
        }

        /* ── Footer ── */
        .footer {
            display: flex;
            align-items: center;
        }

        .brand {
            font-size: 13px;
            font-weight: 800;
            letter-spacing: 2.5px;
            text-transform: uppercase;
            color: rgba(255,255,255,0.9);
        }
        .brand span:first-child { color: var(--orange); }
        .brand-sub {
            font-size: 10px;
            font-weight: 400;
            letter-spacing: 1.5px;
            color: rgba(255,255,255,0.3);
            display: block;
            margin-top: 2px;
        }

        .section-label {
            font-family: 'DM Mono', monospace;
            font-size: 10px;
            font-weight: 500;
            letter-spacing: 2px;
            text-transform: uppercase;
            color: rgba(255,255,255,0.25);
            margin-bottom: 14px;
        }

        /* status row */
        .status-row {
            display: flex;
            gap: 16px;
            margin-top: 24px;
            padding-top: 20px;
            border-top: 1px solid rgba(255,255,255,0.06);
        }
        .status-dot-wrap {
            display: flex;
            align-items: center;
            gap: 6px;
        }
        .status-dot {
            width: 7px; height: 7px;
            border-radius: 50%;
        }
        .status-dot.red    { background: var(--error-red);  box-shadow: 0 0 6px rgba(255,59,59,0.6); animation: blink 1.4s infinite; }
        .status-dot.yellow { background: #F59E0B; box-shadow: 0 0 6px rgba(245,158,11,0.5); animation: blink 1.4s 0.5s infinite; }
        .status-dot.green  { background: #22C55E; box-shadow: 0 0 6px rgba(34,197,94,0.5); }
        .status-label {
            font-family: 'DM Mono', monospace;
            font-size: 10px;
            color: rgba(255,255,255,0.3);
            letter-spacing: 0.5px;
        }

        /* responsive: stack on small screens */
        @media (max-width: 560px) {
            .card { grid-template-columns: 1fr; max-width: 400px; }
            .card-left { border-right: none; border-bottom: 1px solid rgba(255,255,255,0.07); padding: 32px 28px 28px; }
            .card-right { padding: 28px 28px 32px; }
            .card-right::before { width: 100%; top: 0; left: 0; right: auto; }
        }

        .timer-wrap {
            font-family: 'DM Mono', monospace;
            font-size: 11px;
            color: rgba(255,255,255,0.25);
            display: flex;
            align-items: center;
            gap: 5px;
        }
        #timer {
            color: var(--orange);
            font-weight: 500;
            transition: color 0.3s;
        }

        /* progress ring */
        .progress-ring-wrap {
            position: relative;
            width: 20px;
            height: 20px;
        }
        .progress-ring {
            transform: rotate(-90deg);
        }
        .ring-track {
            fill: none;
            stroke: rgba(255,255,255,0.08);
            stroke-width: 2;
        }
        .ring-fill {
            fill: none;
            stroke: var(--orange);
            stroke-width: 2;
            stroke-linecap: round;
            stroke-dasharray: 50.27;
            stroke-dashoffset: 0;
            transition: stroke-dashoffset 1s linear;
        }
    </style>
</head>
<body>

    <div class="bg"></div>
    <div class="bg-overlay"></div>
    <div class="orb orb-1"></div>
    <div class="orb orb-2"></div>

    <div class="card">

        <!-- LEFT PANEL: Branding + Status -->
        <div class="card-left">
            <div>
                <div class="brand" style="margin-bottom:32px;">UTH<span>AO</span> <span class="brand-sub">Logistics</span></div>

                <div class="icon-wrap" style="margin: 0 0 28px;">
                    <div class="icon-bg"></div>
                    <div class="icon-pulse"></div>
                    <div class="icon-pulse-2"></div>
                    <div class="icon-svg">
                        <div class="signal-bars">
                            <div class="bar"></div>
                            <div class="bar"></div>
                            <div class="bar"></div>
                            <div class="bar"></div>
                        </div>
                    </div>
                </div>

                <div class="pill" style="margin-bottom:18px;">
                    <span class="pill-dot"></span>
                    Database Offline
                </div>

                <h1>Connection<br><span>Lost</span></h1>
                <p style="margin-bottom:0;">We can't reach our servers right now. Check your network and try again.</p>
            </div>

            <div class="footer" style="margin-top:32px;">
                <div class="timer-wrap">
                    <div class="progress-ring-wrap">
                        <svg class="progress-ring" width="20" height="20" viewBox="0 0 20 20">
                            <circle class="ring-track" cx="10" cy="10" r="8"/>
                            <circle class="ring-fill" id="ring" cx="10" cy="10" r="8"/>
                        </svg>
                    </div>
                    Auto-retry in <span id="timer">30</span>s
                </div>
            </div>
        </div>

        <!-- RIGHT PANEL: Actions + Tips -->
        <div class="card-right">
            <div>
                <div class="section-label">Actions</div>
                <div class="actions" style="flex-direction:column; margin-bottom:28px;">
                    <button onclick="handleRetry()" class="btn btn-primary">
                        <span class="spin">↻</span> Retry Connection
                    </button>
                    <button onclick="history.back()" class="btn btn-secondary">
                        ← Go Back
                    </button>
                </div>

                <div class="divider" style="margin-bottom:24px;"></div>

                <div class="tips">
                    <div class="tips-header">Quick fixes</div>
                    <div class="tip-item">
                        <span class="tip-num">01</span>
                        <span>Verify your internet connection is active</span>
                    </div>
                    <div class="tip-item">
                        <span class="tip-num">02</span>
                        <span>Wait a moment then retry the request</span>
                    </div>
                    <div class="tip-item">
                        <span class="tip-num">03</span>
                        <span>Clear browser cache &amp; cookies</span>
                    </div>
                </div>
            </div>

            <!-- Status indicator row -->
            <div class="status-row">
                <div class="status-dot-wrap">
                    <span class="status-dot red"></span>
                    <span class="status-label">Database</span>
                </div>
                <div class="status-dot-wrap">
                    <span class="status-dot yellow"></span>
                    <span class="status-label">Network</span>
                </div>
                <div class="status-dot-wrap">
                    <span class="status-dot green"></span>
                    <span class="status-label">Client</span>
                </div>
            </div>
        </div>

    </div>

    <script>
        const TOTAL = 30;
        let seconds = TOTAL;
        const timerEl = document.getElementById('timer');
        const ring = document.getElementById('ring');
        const circumference = 2 * Math.PI * 8; // 50.27

        function updateRing(s) {
            const offset = circumference * (1 - s / TOTAL);
            ring.style.strokeDashoffset = offset;
        }

        updateRing(TOTAL);

        const countdown = setInterval(() => {
            seconds--;
            timerEl.textContent = seconds;
            updateRing(seconds);
            if (seconds <= 0) {
                clearInterval(countdown);
                timerEl.style.color = 'rgba(255,255,255,0.25)';
            }
        }, 1000);

        function handleRetry() {
            const btn = document.querySelector('.btn-primary');
            btn.textContent = '⋯ Checking';
            btn.style.opacity = '0.7';
            btn.disabled = true;
            setTimeout(() => location.reload(), 400);
        }

        setTimeout(() => {
            fetch('/health-check')
                .then(r => { if (r.ok) location.reload(); })
                .catch(() => {});
        }, 30000);
    </script>

</body>
</html>
'''

def create_app():
    import click

    app = Flask(__name__)
    app.config.from_object(Config)
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key')

    # Mail config
    app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
    app.config['MAIL_PORT'] = int(os.environ.get('MAIL_PORT', 587))
    app.config['MAIL_USE_TLS'] = True
    app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME')
    app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')
    app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('MAIL_DEFAULT_SENDER', 'noreply@uthao.com')

    # Set DB as available by default
    app.config['DB_AVAILABLE'] = True

    db.init_app(app)
    mail.init_app(app)
    migrate.init_app(app, db)

    # Register blueprints
    from blueprints.main import main_bp
    from blueprints.auth import auth_bp
    from blueprints.user import user_bp
    from blueprints.admin import admin_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(user_bp, url_prefix='/user')
    app.register_blueprint(admin_bp, url_prefix='/admin')

    init_socket_events(socketio)

    # Login manager
    from flask_login import LoginManager
    login_mgr = LoginManager()
    login_mgr.init_app(app)
    login_mgr.login_view = 'auth.login'

    @login_mgr.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # Uploads route
    from flask import send_from_directory

    @app.route('/uploads/<path:filename>')
    def uploaded_file(filename):
        upload_folder = app.config.get(
            'UPLOAD_FOLDER',
            os.path.join(app.root_path, 'static', 'uploads')
        )
        return send_from_directory(upload_folder, filename)

    @app.context_processor
    def utility_processor():
        return dict(now=datetime.utcnow)

    @app.cli.command("reset-admin")
    @click.option("--email", default="admin@uthao.com")
    @click.option("--password", prompt=True, hide_input=True, confirmation_prompt=True)
    @click.option("--name", default="Admin User")
    def reset_admin(email, password, name):
        existing = User.query.filter_by(email=email).first()
        if existing:
            db.session.delete(existing)
            db.session.commit()
        admin = User(
            email=email,
            password_hash=generate_password_hash(password),
            full_name=name,
            is_admin=True,
            is_active=True,
            created_at=datetime.utcnow()
        )
        db.session.add(admin)
        db.session.commit()
        print(f"Admin created: {email}")

    # Try to connect to DB on startup
    with app.app_context():
        try:
            db.create_all()
            _seed_default_users()
            init_socket_events(socketio)
            logger.info("Database tables created successfully")
            app.config['DB_AVAILABLE'] = True
        except OperationalError as e:
            error_str = str(e).lower()
            logger.error(f"Database connection failed during startup: {e}")
            
            if any(keyword in error_str for keyword in [
                'could not translate host name', 
                'could not connect',
                'connection',
                'timeout',
                'refused',
                'network',
                'dns'
            ]):
                app.config['DB_AVAILABLE'] = False
                logger.warning("Application starting in OFFLINE mode - database unavailable")
            else:
                raise

    # Health check endpoint
    @app.route('/health-check')
    def health_check():
        try:
            db.session.execute(text('SELECT 1'))
            db.session.commit()
            app.config['DB_AVAILABLE'] = True
            return {'status': 'ok', 'database': 'connected'}, 200
        except Exception as e:
            app.config['DB_AVAILABLE'] = False
            return {'status': 'error', 'database': 'disconnected'}, 503

    # Global error handler for database errors
    @app.errorhandler(OperationalError)
    def handle_operational_error(error):
        """Handle database connection errors."""
        logger.error(f"Database error: {error}")
        app.config['DB_AVAILABLE'] = False
        
        # Return offline page for all requests
        if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return {'success': False, 'error': 'Network error. Please check your internet connection.'}, 503
        
        response = make_response(OFFLINE_HTML, 503)
        response.headers['Content-Type'] = 'text/html'
        return response

    # Check DB on each request
    @app.before_request
    def check_db():
        # Skip health check and static files
        if request.endpoint in ['health_check', 'static', 'uploaded_file']:
            return None
        
        # If DB is marked unavailable, try to reconnect
        if not app.config.get('DB_AVAILABLE', True):
            try:
                db.session.execute(text('SELECT 1'))
                db.session.commit()
                app.config['DB_AVAILABLE'] = True
                logger.info("Database reconnected")
                return None
            except Exception:
                # Still down - return offline page
                if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return {'success': False, 'error': 'Network error. Check connection.'}, 503
                
                response = make_response(OFFLINE_HTML, 503)
                response.headers['Content-Type'] = 'text/html'
                return response

    return app

def _seed_default_users():
    from werkzeug.security import generate_password_hash
    from datetime import datetime

    if not User.query.filter_by(email='admin@uthao.com').first():
        db.session.add(User(
            email='admin@uthao.com',
            password_hash=generate_password_hash('Admin@1234'),
            full_name='Admin User',
            is_admin=True, is_active=True,
            created_at=datetime.utcnow()
        ))
        print('✓ Admin created')

    if not User.query.filter_by(email='1stpassabite@gmail.com').first():
        db.session.add(User(
            email='1stpassabite@gmail.com',
            password_hash=generate_password_hash('User@1234'),
            full_name='Test User',
            is_admin=False, is_active=True,
            created_at=datetime.utcnow()
        ))
        print('✓ User created')

    db.session.commit()


# from flask import Flask
# from config import Config
# from models import User, Plan, PLANS
# from flask_login import LoginManager
# from flask_migrate import Migrate
# from datetime import datetime, timedelta
# from sqlalchemy import or_
# import os
# from flask_socketio import SocketIO
# from socket_events import socketio, init_socket_events


# # Create socketio here
# socketio = SocketIO(cors_allowed_origins="*", async_mode='threading')


# def create_app():
#     from werkzeug.security import generate_password_hash
#     import click
#     from extensions import db, mail, login_manager, migrate

#     app = Flask(__name__)

#     app.config.from_object(Config)

#     db.init_app(app)
#     mail.init_app(app)
#     migrate.init_app(app, db)

#     # Initialize SocketIO
#     socketio.init_app(app)

#     login_manager = LoginManager()
#     login_manager.init_app(app)
#     login_manager.login_view = 'auth.login'

#     from blueprints.main import main_bp
#     from blueprints.auth import auth_bp
#     from blueprints.user import user_bp
#     from blueprints.admin import admin_bp

#     app.register_blueprint(main_bp)
#     app.register_blueprint(auth_bp, url_prefix='/auth')
#     app.register_blueprint(user_bp, url_prefix='/user')
#     app.register_blueprint(admin_bp, url_prefix='/admin')

#     # Config
#     app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key')
    
#     # Mail config - UPDATE THESE with your actual SMTP settings
#     app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
#     app.config['MAIL_PORT'] = int(os.environ.get('MAIL_PORT', 587))
#     app.config['MAIL_USE_TLS'] = os.environ.get('MAIL_USE_TLS', 'true').lower() in ['true', '1', 'yes']
#     app.config['MAIL_USE_SSL'] = os.environ.get('MAIL_USE_SSL', 'false').lower() in ['true', '1', 'yes']
#     app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME')  # Your email
#     app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')  # Your app password
#     app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('MAIL_DEFAULT_SENDER', 'noreply@uthao.com')
    

#     from flask import send_from_directory

#     # At the bottom of app.py or in your user blueprint
#     @app.route('/uploads/<path:filename>')
#     def uploaded_file(filename):
#         upload_folder = app.config.get('UPLOAD_FOLDER', os.path.join(app.root_path, 'static', 'uploads'))
#         return send_from_directory(upload_folder, filename)

#     @login_manager.user_loader
#     def load_user(user_id):
#         from models import User
#         return User.query.get(int(user_id))

#     @app.context_processor
#     def utility_processor():
#         from datetime import datetime
#         return dict(now=datetime.utcnow)

    
#     @app.cli.command("reset-admin")
#     @click.option("--email", default="admin@uthao.com", help="Admin email")
#     @click.option("--password", prompt=True, hide_input=True, confirmation_prompt=True)
#     @click.option("--name", default="Admin User", help="Admin full name")
#     def reset_admin(email, password, name):
#         """Delete existing admin and create a new one."""
#         from models import User
        
#         # Find existing admin
#         existing_admin = User.query.filter_by(email=email).first()
        
#         if existing_admin:
#             print(f"Deleting existing admin: {email}")
#             db.session.delete(existing_admin)
#             db.session.commit()
        
#         # Create new admin
#         new_admin = User(
#             email=email,
#             password_hash=generate_password_hash(password),
#             full_name=name,
#             is_admin=True,
#             is_active=True,
#             created_at=datetime.utcnow()
#         )
        
#         db.session.add(new_admin)
#         db.session.commit()
        
#         print(f"New admin created successfully: {email}")

#     with app.app_context():
#         db.create_all()


#     with app.app_context():
#         import socket_events

#     # with app.app_context():
#     #     db.create_all()
#     #     # Create admin user if not exists
#     #     from models import User
#     #     if not User.query.filter_by(email='admin@uthao.com').first():
#     #         from werkzeug.security import generate_password_hash
#     #         admin = User(
#     #             email='admin@uthao.com',
#     #             password_hash=generate_password_hash('admin123'),
#     #             full_name='Admin User',
#     #             is_admin=True
#     #         )
#     #         db.session.add(admin)
#     #         db.session.commit()
#     #         print('admin created')
#     # with app.app_context():
#     #     users = User.query.filter(User.currency.is_(None)).all()
#     #     for user in users:
#     #         user.currency = 'USD'
#     #     db.session.commit()
#     #     print(f"Updated {len(users)} users to USD")

#     # with app.app_context():
#     #     # Get users without created_at
#     #     users_without_created_at = User.query.filter(
#     #         User.created_at.is_(None)
#     #     ).all()

#     #     print(f"Found {len(users_without_created_at)} users without created_at")

#     #     # Update them
#     #     now = datetime.utcnow()

#     #     for user in users_without_created_at:
#     #         user.created_at = now

#     #     db.session.commit()

#     #     print("All missing created_at values updated successfully.")

#     # with app.app_context():
#     #     import json

#     #     for i, (key, data) in enumerate(PLANS.items()):
#     #         if Plan.query.filter_by(plan_key=key).first():
#     #             continue
#     #         p = Plan(
#     #             plan_key=key, name=data['name'], price_usd=data['price_usd'],
#     #             shipments=data.get('shipments'), is_active=True,
#     #             is_featured=(key == 'professional'), sort_order=i,
#     #         )
#     #         p._features = json.dumps(data.get('features', []))
#     #         db.session.add(p)
#     #     db.session.commit()
#     #     print('Done')

#     #     # Find users that are not active or NULL
#     #     users_to_activate = User.query.filter(
#     #         or_(
#     #             User.is_active == False,
#     #             User.is_active.is_(None)
#     #         )
#     #     )

#     #     count = users_to_activate.count()
#     #     print(f"Found {count} users to activate")

#     #     # Bulk update
#     #     users_to_activate.update(
#     #         {User.is_active: True},
#     #         synchronize_session=False
#     #     )

#     #     db.session.commit()

#     #     print("All inactive users have been set to active.")

#     return app
