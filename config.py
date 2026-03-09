import os
from datetime import datetime, timedelta


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key'
    SQLALCHEMY_DATABASE_URI = 'sqlite:///courier.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
     # Admin Settings
    ADMIN_SETUP_SECRET = os.environ.get('ADMIN_SETUP_SECRET', 'uthao-admin-setup-2024-change-this')
    
    # Security
    MAX_LOGIN_ATTEMPTS = 5
    LOGIN_TIMEOUT = 300  # 5 minutes
    
    # Session
    PERMANENT_SESSION_LIFETIME = timedelta(hours=12)
    
    MAIL_SERVER = os.getenv('MAIL_SERVER', 'smtp.gmail.com')
    MAIL_PORT = int(os.getenv('MAIL_PORT', 587))
    MAIL_USE_TLS = os.getenv('MAIL_USE_TLS', 'True').lower() == 'true'
    MAIL_USERNAME = os.getenv('MAIL_USERNAME', os.getenv('SMTP_EMAIL'))
    MAIL_PASSWORD = os.getenv('MAIL_PASSWORD', os.getenv('SMTP_PASSWORD'))
    MAIL_DEFAULT_SENDER = os.getenv('MAIL_DEFAULT_SENDER', os.getenv('SMTP_EMAIL'))

    