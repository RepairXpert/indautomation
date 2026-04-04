"""
Customer Account Management
Account types, supplier connections, resale mode, order history
"""

import sqlite3
import json
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from enum import Enum

logger = logging.getLogger(__name__)


class AccountTier(Enum):
    """Customer account tiers"""
    FREE = "free"
    PRO = "pro"
    ENTERPRISE = "enterprise"


class AccountsDatabase:
    """SQLite database for customer accounts"""

    def __init__(self, db_path: str = "accounts.db"):
        self.db_path = db_path
        self.conn = None
        self.init_database()

    def init_database(self):
        """Initialize database schema"""
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        cursor = self.conn.cursor()

        # Customers table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS customers (
                id INTEGER PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                company_name TEXT,
                account_tier TEXT DEFAULT 'free',
                is_reseller BOOLEAN DEFAULT 0,
                monthly_lookups INTEGER DEFAULT 0,
                lookup_limit INTEGER DEFAULT 3,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Supplier accounts table (customer's accounts with suppliers)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS supplier_accounts (
                id INTEGER PRIMARY KEY,
                customer_id INTEGER NOT NULL,
                supplier TEXT NOT NULL,
                account_number TEXT,
                username TEXT,
                discount_percent REAL DEFAULT 0,
                negotiated_pricing JSON,
                is_active BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (customer_id) REFERENCES customers(id),
                UNIQUE(customer_id, supplier)
            )
        """)

        # Order history table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY,
                customer_id INTEGER NOT NULL,
                order_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                parts JSON NOT NULL,
                total_cost REAL,
                supplier TEXT,
                order_number TEXT,
                status TEXT DEFAULT 'pending',
                notes TEXT,
                FOREIGN KEY (customer_id) REFERENCES customers(id)
            )
        """)

        # Saved parts lists (wishlist/shopping cart)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS saved_parts_lists (
                id INTEGER PRIMARY KEY,
                customer_id INTEGER NOT NULL,
                list_name TEXT NOT NULL,
                description TEXT,
                parts JSON,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (customer_id) REFERENCES customers(id),
                UNIQUE(customer_id, list_name)
            )
        """)

        # Price alerts
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS price_alerts (
                id INTEGER PRIMARY KEY,
                customer_id INTEGER NOT NULL,
                part_number TEXT NOT NULL,
                target_price REAL NOT NULL,
                current_price REAL,
                is_active BOOLEAN DEFAULT 1,
                alert_sent BOOLEAN DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (customer_id) REFERENCES customers(id),
                UNIQUE(customer_id, part_number)
            )
        """)

        # Create indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_customer_email ON customers(email)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_supplier_account ON supplier_accounts(customer_id, supplier)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_order_customer ON orders(customer_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_alert_active ON price_alerts(is_active)")

        self.conn.commit()
        logger.info(f"Accounts database initialized: {self.db_path}")

    def close(self):
        """Close database connection"""
        if self.conn:
            self.conn.close()

    def create_customer(self, email: str, company_name: str = "",
                       account_tier: str = "free", is_reseller: bool = False) -> int:
        """Create new customer account"""
        cursor = self.conn.cursor()

        tier = account_tier.lower()
        lookup_limits = {
            "free": 3,
            "pro": 1000,
            "enterprise": 10000
        }
        lookup_limit = lookup_limits.get(tier, 3)

        try:
            cursor.execute("""
                INSERT INTO customers (email, company_name, account_tier, is_reseller, lookup_limit)
                VALUES (?, ?, ?, ?, ?)
            """, (email, company_name, tier, is_reseller, lookup_limit))

            self.conn.commit()
            customer_id = cursor.lastrowid
            logger.info(f"Created customer: {email} (ID: {customer_id})")
            return customer_id
        except sqlite3.IntegrityError:
            logger.warning(f"Customer already exists: {email}")
            return self.get_customer_id(email)

    def get_customer_id(self, email: str) -> Optional[int]:
        """Get customer ID by email"""
        cursor = self.conn.cursor()
        cursor.execute("SELECT id FROM customers WHERE email = ?", (email,))
        row = cursor.fetchone()
        return row[0] if row else None

    def get_customer(self, customer_id: int) -> Optional[Dict]:
        """Get customer details"""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT id, email, company_name, account_tier, is_reseller,
                   monthly_lookups, lookup_limit, created_at, updated_at
            FROM customers WHERE id = ?
        """, (customer_id,))

        row = cursor.fetchone()
        if not row:
            return None

        return {
            'id': row[0],
            'email': row[1],
            'company_name': row[2],
            'account_tier': row[3],
            'is_reseller': bool(row[4]),
            'monthly_lookups': row[5],
            'lookup_limit': row[6],
            'created_at': row[7],
            'updated_at': row[8]
        }

    def check_lookup_limit(self, customer_id: int) -> bool:
        """Check if customer has remaining lookups"""
        customer = self.get_customer(customer_id)
        if not customer:
            return False

        return customer['monthly_lookups'] < customer['lookup_limit']

    def increment_lookup_count(self, customer_id: int):
        """Increment monthly lookup counter"""
        cursor = self.conn.cursor()
        cursor.execute("""
            UPDATE customers SET monthly_lookups = monthly_lookups + 1
            WHERE id = ?
        """, (customer_id,))
        self.conn.commit()

    def reset_monthly_lookups(self):
        """Reset monthly lookup counters (call on 1st of month)"""
        cursor = self.conn.cursor()
        cursor.execute("UPDATE customers SET monthly_lookups = 0")
        self.conn.commit()
        logger.info("Reset all monthly lookup counters")

    def upgrade_account(self, customer_id: int, new_tier: str):
        """Upgrade customer account tier"""
        cursor = self.conn.cursor()

        lookup_limits = {
            "free": 3,
            "pro": 1000,
            "enterprise": 10000
        }
        new_limit = lookup_limits.get(new_tier.lower(), 3)

        cursor.execute("""
            UPDATE customers SET account_tier = ?, lookup_limit = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (new_tier.lower(), new_limit, customer_id))

        self.conn.commit()
        logger.info(f"Upgraded customer {customer_id} to {new_tier}")

    def add_supplier_account(self, customer_id: int, supplier: str,
                            account_number: str = "", username: str = "",
                            discount_percent: float = 0,
                            negotiated_pricing: Dict = None) -> int:
        """Link supplier account to customer"""
        cursor = self.conn.cursor()

        negotiated_json = json.dumps(negotiated_pricing or {})

        try:
            cursor.execute("""
                INSERT INTO supplier_accounts (customer_id, supplier, account_number,
                                             username, discount_percent, negotiated_pricing)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(customer_id, supplier) DO UPDATE SET
                    account_number = excluded.account_number,
                    username = excluded.username,
                    discount_percent = excluded.discount_percent,
                    negotiated_pricing = excluded.negotiated_pricing,
                    updated_at = CURRENT_TIMESTAMP
            """, (customer_id, supplier, account_number, username, discount_percent, negotiated_json))

            self.conn.commit()
            return cursor.lastrowid
        except Exception as e:
            logger.error(f"Failed to add supplier account: {e}")
            return None

    def get_supplier_accounts(self, customer_id: int) -> List[Dict]:
        """Get all supplier accounts for customer"""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT id, supplier, account_number, username, discount_percent,
                   negotiated_pricing, is_active
            FROM supplier_accounts WHERE customer_id = ?
        """, (customer_id,))

        accounts = []
        for row in cursor.fetchall():
            accounts.append({
                'id': row[0],
                'supplier': row[1],
                'account_number': row[2],
                'username': row[3],
                'discount_percent': row[4],
                'negotiated_pricing': json.loads(row[5]) if row[5] else {},
                'is_active': bool(row[6])
            })

        return accounts

    def record_order(self, customer_id: int, parts: List[Dict], total_cost: float,
                    supplier: str = None, order_number: str = None, notes: str = "") -> int:
        """Record order in history"""
        cursor = self.conn.cursor()

        parts_json = json.dumps(parts)

        cursor.execute("""
            INSERT INTO orders (customer_id, parts, total_cost, supplier, order_number, notes)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (customer_id, parts_json, total_cost, supplier, order_number, notes))

        self.conn.commit()
        order_id = cursor.lastrowid
        logger.info(f"Recorded order {order_id} for customer {customer_id}")
        return order_id

    def get_order_history(self, customer_id: int, limit: int = 50) -> List[Dict]:
        """Get customer's order history"""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT id, order_date, parts, total_cost, supplier, order_number, status, notes
            FROM orders WHERE customer_id = ?
            ORDER BY order_date DESC
            LIMIT ?
        """, (customer_id, limit))

        orders = []
        for row in cursor.fetchall():
            orders.append({
                'id': row[0],
                'order_date': row[1],
                'parts': json.loads(row[2]) if row[2] else [],
                'total_cost': row[3],
                'supplier': row[4],
                'order_number': row[5],
                'status': row[6],
                'notes': row[7]
            })

        return orders

    def save_parts_list(self, customer_id: int, list_name: str,
                       parts: List[Dict], description: str = "") -> int:
        """Save a list of parts (wishlist/cart)"""
        cursor = self.conn.cursor()

        parts_json = json.dumps(parts)

        try:
            cursor.execute("""
                INSERT INTO saved_parts_lists (customer_id, list_name, description, parts)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(customer_id, list_name) DO UPDATE SET
                    parts = excluded.parts,
                    description = excluded.description,
                    updated_at = CURRENT_TIMESTAMP
            """, (customer_id, list_name, description, parts_json))

            self.conn.commit()
            return cursor.lastrowid
        except Exception as e:
            logger.error(f"Failed to save parts list: {e}")
            return None

    def get_parts_lists(self, customer_id: int) -> List[Dict]:
        """Get customer's saved parts lists"""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT id, list_name, description, parts, created_at, updated_at
            FROM saved_parts_lists WHERE customer_id = ?
            ORDER BY updated_at DESC
        """, (customer_id,))

        lists = []
        for row in cursor.fetchall():
            lists.append({
                'id': row[0],
                'list_name': row[1],
                'description': row[2],
                'parts': json.loads(row[3]) if row[3] else [],
                'created_at': row[4],
                'updated_at': row[5]
            })

        return lists

    def create_price_alert(self, customer_id: int, part_number: str,
                          target_price: float) -> int:
        """Create price alert for a part"""
        cursor = self.conn.cursor()

        try:
            cursor.execute("""
                INSERT INTO price_alerts (customer_id, part_number, target_price)
                VALUES (?, ?, ?)
                ON CONFLICT(customer_id, part_number) DO UPDATE SET
                    target_price = excluded.target_price,
                    alert_sent = 0
            """, (customer_id, part_number, target_price))

            self.conn.commit()
            return cursor.lastrowid
        except Exception as e:
            logger.error(f"Failed to create price alert: {e}")
            return None

    def get_active_price_alerts(self) -> List[Dict]:
        """Get all active price alerts"""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT id, customer_id, part_number, target_price, current_price
            FROM price_alerts WHERE is_active = 1 AND alert_sent = 0
        """)

        alerts = []
        for row in cursor.fetchall():
            alerts.append({
                'id': row[0],
                'customer_id': row[1],
                'part_number': row[2],
                'target_price': row[3],
                'current_price': row[4]
            })

        return alerts

    def mark_alert_sent(self, alert_id: int):
        """Mark price alert as sent"""
        cursor = self.conn.cursor()
        cursor.execute("""
            UPDATE price_alerts SET alert_sent = 1
            WHERE id = ?
        """, (alert_id,))
        self.conn.commit()

    def update_alert_price(self, alert_id: int, current_price: float):
        """Update current price in alert"""
        cursor = self.conn.cursor()
        cursor.execute("""
            UPDATE price_alerts SET current_price = ?
            WHERE id = ?
        """, (current_price, alert_id))
        self.conn.commit()
