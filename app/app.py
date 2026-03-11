# app.py
from flask import Flask
from app.config import Config
from flask_socketio import SocketIO
import os

socketio = SocketIO(cors_allowed_origins="*", async_mode='threading', logger=True, engineio_logger=True)

def create_app():
    from werkzeug.security import generate_password_hash
    import click
    from app.extensions import db, mail, login_manager, migrate

    app = Flask(__name__)
    app.config.from_object(Config)
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key')

    app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
    app.config['MAIL_PORT'] = int(os.environ.get('MAIL_PORT', 587))
    app.config['MAIL_USE_TLS'] = True
    app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME')
    app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')
    app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('MAIL_DEFAULT_SENDER', 'noreply@uthao.com')

    db.init_app(app)
    mail.init_app(app)
    migrate.init_app(app, db)

    socketio.init_app(app)

    from app.blueprints.main import main_bp
    from app.blueprints.auth import auth_bp
    from app.blueprints.user import user_bp
    from app.blueprints.admin import admin_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(user_bp, url_prefix='/user')
    app.register_blueprint(admin_bp, url_prefix='/admin')

    from app.socket_events import init_socket_events
    init_socket_events(socketio)

    from flask_login import LoginManager
    login_mgr = LoginManager()
    login_mgr.init_app(app)
    login_mgr.login_view = 'auth.login'

    @login_mgr.user_loader
    def load_user(user_id):
        from app.models import User
        return User.query.get(int(user_id))

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
        from datetime import datetime
        return dict(now=datetime.utcnow)

    @app.cli.command("reset-admin")
    @click.option("--email", default="admin@uthao.com")
    @click.option("--password", prompt=True, hide_input=True, confirmation_prompt=True)
    @click.option("--name", default="Admin User")
    def reset_admin(email, password, name):
        from app.models import User
        from datetime import datetime
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

    with app.app_context():
        db.create_all()
        _seed_default_users(db, generate_password_hash)

    return app


def _seed_default_users(db, generate_password_hash):
    """Create default admin and normal user if they don't exist."""
    from app.models import User
    from datetime import datetime

    # ── Default admin ────────────────────────────────────────────────
    if not User.query.filter_by(email='admin@uthao.com').first():
        admin = User(
            email='admin@uthao.com',
            password_hash=generate_password_hash('Admin@1234'),
            full_name='Admin User',
            is_admin=True,
            is_active=True,
            created_at=datetime.utcnow()
        )
        db.session.add(admin)
        print('✓ Default admin created → admin@uthao.com / Admin@1234')

    # ── Default normal user ──────────────────────────────────────────
    if not User.query.filter_by(email='1stpassabite@gmail.com').first():
        user = User(
            email='1stpassabite@gmail.com',
            password_hash=generate_password_hash('User@1234'),
            full_name='Test User',
            is_admin=False,
            is_active=True,
            created_at=datetime.utcnow()
        )
        db.session.add(user)
        print('✓ Default user created → 1stpassabite@gmail.com / User@1234')

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
