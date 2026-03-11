import sqlite3
import os

# Path to your SQLite database
db_path = 'instance/courier.db'  # Adjust path as needed

def migrate_database():
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Check if column exists
    cursor.execute("PRAGMA table_info(payment_request)")
    columns = [col[1] for col in cursor.fetchall()]
    
    if 'payment_method_id' not in columns:
        print("Adding payment_method_id column...")
        cursor.execute("ALTER TABLE payment_request ADD COLUMN payment_method_id INTEGER")
        conn.commit()
        print("Column added successfully!")
    else:
        print("Column already exists.")
    
    # Check if payment_method table exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='payment_method'")
    if not cursor.fetchone():
        print("Creating payment_method table...")
        cursor.execute('''
            CREATE TABLE payment_method (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name VARCHAR(50) NOT NULL,
                code VARCHAR(20) UNIQUE NOT NULL,
                display_name VARCHAR(100) NOT NULL,
                description TEXT,
                icon VARCHAR(50),
                wallet_address VARCHAR(500),
                qr_code_url VARCHAR(500),
                network VARCHAR(50),
                bank_name VARCHAR(100),
                account_number VARCHAR(100),
                account_name VARCHAR(100),
                routing_number VARCHAR(50),
                swift_code VARCHAR(50),
                paypal_email VARCHAR(120),
                paypal_link VARCHAR(500),
                is_active BOOLEAN DEFAULT 1,
                sort_order INTEGER DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Insert default payment methods
        methods = [
            ('USDT (TRC20)', 'usdt', 'USDT - Tether (TRC20)', 'Fast and low-fee USDT transfers on Tron network', 'fa-coins', 
             'YOUR_USDT_WALLET', '/static/images/payments/usdt-qr.png', 'TRC20', None, None, None, None, None, None, None, 1, 1),
            ('Bitcoin', 'bitcoin', 'Bitcoin (BTC)', 'Secure Bitcoin payments with network confirmation', 'fa-bitcoin',
             'YOUR_BTC_WALLET', '/static/images/payments/bitcoin-qr.png', 'BTC', None, None, None, None, None, None, None, 1, 2),
            ('Bank Transfer', 'bank_transfer', 'Bank Transfer (NGN/USD)', 'Direct bank transfer to our corporate account', 'fa-university',
             None, None, None, 'First Bank of Nigeria', '0123456789', 'UTHAO Logistics Ltd', 'FBNINGLA', 'FBNINGLA', None, None, 1, 3),
            ('PayPal', 'paypal', 'PayPal', 'Pay securely with your PayPal account', 'fa-paypal',
             None, None, None, None, None, None, None, None, 'payments@uthao.com', 'https://paypal.me/uthao', 1, 4),
        ]
        
        cursor.executemany('''
            INSERT INTO payment_method 
            (name, code, display_name, description, icon, wallet_address, qr_code_url, network, 
             bank_name, account_number, account_name, routing_number, swift_code, paypal_email, paypal_link, is_active, sort_order)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', methods)
        
        conn.commit()
        print("Payment methods created!")
    else:
        print("payment_method table already exists.")
    
    conn.close()
    print("Migration complete!")

if __name__ == '__main__':
    migrate_database()