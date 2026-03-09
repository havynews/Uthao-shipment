# from models import db, Shipment, ShipmentEvent, Package, Subscription, PLANS, \
#     NotificationPreference, CURRENCIES, PaymentRequest, PaymentMethod
# from app import create_app

# app = create_app()

# def seed_payment_methods():
#     methods = [
#         {
#             'name': 'USDT (TRC20)',
#             'code': 'usdt',
#             'display_name': 'USDT - Tether (TRC20)',
#             'description': 'Fast and low-fee USDT transfers on Tron network',
#             'icon': 'fa-coins',
#             'network': 'TRC20',
#             'wallet_address': 'YOUR_USDT_TRC20_WALLET_ADDRESS_HERE',
#             'qr_code_url': '/static/images/payments/usdt-qr.png',
#             'sort_order': 1
#         },
#         {
#             'name': 'Bitcoin',
#             'code': 'bitcoin',
#             'display_name': 'Bitcoin (BTC)',
#             'description': 'Secure Bitcoin payments with network confirmation',
#             'icon': 'fa-bitcoin',
#             'network': 'BTC',
#             'wallet_address': 'YOUR_BTC_WALLET_ADDRESS_HERE',
#             'qr_code_url': '/static/images/payments/bitcoin-qr.png',
#             'sort_order': 2
#         },
#         {
#             'name': 'Bank Transfer',
#             'code': 'bank_transfer',
#             'display_name': 'Bank Transfer (NGN/USD)',
#             'description': 'Direct bank transfer to our corporate account',
#             'icon': 'fa-university',
#             'bank_name': 'First Bank of Nigeria',
#             'account_name': 'UTHAO Logistics Ltd',
#             'account_number': '0123456789',
#             'routing_number': 'FBNINGLA',
#             'swift_code': 'FBNINGLA',
#             'sort_order': 3
#         },
#         {
#             'name': 'PayPal',
#             'code': 'paypal',
#             'display_name': 'PayPal',
#             'description': 'Pay securely with your PayPal account',
#             'icon': 'fa-paypal',
#             'paypal_email': 'payments@uthao.com',
#             'paypal_link': 'https://paypal.me/uthao',
#             'sort_order': 4
#         }
#     ]
    
#     for method_data in methods:
#         existing = PaymentMethod.query.filter_by(code=method_data['code']).first()
#         if not existing:
#             pm = PaymentMethod(**method_data)
#             db.session.add(pm)
    
#     db.session.commit()
#     print("Payment methods seeded successfully!")


# import sqlalchemy as sa

# with app.app_context():
#     # Drop existing tables
#     from models import db, PaymentMethod

#     # Fix Bitcoin
#     bitcoin = PaymentMethod.query.filter_by(code='bitcoin').first()
#     if bitcoin:
#         bitcoin.icon = 'fa-brands fa-bitcoin'  # or 'fa-brands fa-btc'
#         print(f"Updated Bitcoin: {bitcoin.icon}")

#     # Fix PayPal
#     paypal = PaymentMethod.query.filter_by(code='paypal').first()
#     if paypal:
#         paypal.icon = 'fa-brands fa-paypal'
#         print(f"Updated PayPal: {paypal.icon}")

#     # Commit changes
#     db.session.commit()
#     print("Done! Icons updated.")



# from app import create_app  # adjust import to match your app factory
# from sqlalchemy import text
# from extensions import db
# # from app import create_app

# app = create_app()

# with app.app_context():
#     with db.engine.connect() as conn:
#         conn.execute(text("DROP TABLE IF EXISTS _alembic_tmp_payment_method"))
#         conn.execute(text("DROP TABLE IF EXISTS _alembic_tmp_notification"))
#         conn.commit()


# from app import create_app
# from extensions import db
# import sqlite3

# app = create_app()
# with app.app_context():
#     # Get the database path from SQLAlchemy
#     db_uri = app.config['SQLALCHEMY_DATABASE_URI']
#     if db_uri.startswith('sqlite:///'):
#         db_path = db_uri.replace('sqlite:///', '')
        
#         conn = sqlite3.connect(db_path)
#         cursor = conn.cursor()
        
#         # Drop all leftover alembic temp tables
#         cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '_alembic_tmp_%'")
#         temp_tables = cursor.fetchall()
        
#         for (table_name,) in temp_tables:
#             print(f"Dropping {table_name}...")
#             cursor.execute(f"DROP TABLE IF EXISTS {table_name}")
        
#         conn.commit()
#         conn.close()
#         print("Cleanup complete!")