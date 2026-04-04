"""
Unified Parts Catalog
SQLite database with parts from all suppliers
"""

import sqlite3
import json
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple, Any
from dataclasses import asdict
import os

from suppliers import PartPrice, PartDetails

logger = logging.getLogger(__name__)


class PartsDatabase:
    """SQLite database for parts catalog"""

    def __init__(self, db_path: str = "parts_catalog.db"):
        self.db_path = db_path
        self.conn = None
        self.init_database()

    def init_database(self):
        """Initialize database schema"""
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        cursor = self.conn.cursor()

        # Main parts table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS parts (
                id INTEGER PRIMARY KEY,
                part_number TEXT UNIQUE NOT NULL,
                manufacturer TEXT,
                description TEXT,
                category TEXT,
                specs JSON,
                datasheet_url TEXT,
                rohs_compliant BOOLEAN DEFAULT 0,
                packaging TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Supplier pricing table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS pricing (
                id INTEGER PRIMARY KEY,
                part_id INTEGER NOT NULL,
                supplier TEXT NOT NULL,
                supplier_part_number TEXT,
                unit_price REAL NOT NULL,
                quantity_available INTEGER,
                lead_time_days INTEGER,
                quantity_breaks JSON,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (part_id) REFERENCES parts(id),
                UNIQUE(part_id, supplier)
            )
        """)

        # Cross-reference table (same part, different suppliers)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS cross_references (
                id INTEGER PRIMARY KEY,
                part_id INTEGER NOT NULL,
                supplier TEXT NOT NULL,
                supplier_part_number TEXT NOT NULL,
                manufacturer_part_number TEXT,
                FOREIGN KEY (part_id) REFERENCES parts(id),
                UNIQUE(supplier, supplier_part_number)
            )
        """)

        # Search index
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS search_index (
                id INTEGER PRIMARY KEY,
                part_id INTEGER NOT NULL,
                search_text TEXT,
                recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (part_id) REFERENCES parts(id)
            )
        """)

        # Price history for trending analysis
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS price_history (
                id INTEGER PRIMARY KEY,
                part_id INTEGER NOT NULL,
                supplier TEXT NOT NULL,
                price REAL NOT NULL,
                quantity_available INTEGER,
                recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (part_id) REFERENCES parts(id)
            )
        """)

        # Create indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_part_number ON parts(part_number)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_category ON parts(category)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_manufacturer ON parts(manufacturer)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_supplier ON pricing(supplier)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_search ON search_index(search_text)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_price_history ON price_history(part_id, supplier)")

        self.conn.commit()
        logger.info(f"Database initialized: {self.db_path}")

    def close(self):
        """Close database connection"""
        if self.conn:
            self.conn.close()

    def add_part(self, part_number: str, manufacturer: str = "", description: str = "",
                 category: str = "", specs: Dict = None, datasheet_url: str = None,
                 rohs_compliant: bool = False, packaging: str = "Individual") -> int:
        """Add a part to the catalog"""
        cursor = self.conn.cursor()

        specs_json = json.dumps(specs or {})

        try:
            cursor.execute("""
                INSERT INTO parts (part_number, manufacturer, description, category, specs,
                                 datasheet_url, rohs_compliant, packaging)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (part_number, manufacturer, description, category, specs_json,
                  datasheet_url, rohs_compliant, packaging))

            self.conn.commit()
            part_id = cursor.lastrowid
            logger.info(f"Added part: {part_number} (ID: {part_id})")
            return part_id
        except sqlite3.IntegrityError:
            logger.warning(f"Part already exists: {part_number}")
            return self.get_part_id(part_number)

    def get_part_id(self, part_number: str) -> Optional[int]:
        """Get part ID by part number"""
        cursor = self.conn.cursor()
        cursor.execute("SELECT id FROM parts WHERE part_number = ?", (part_number,))
        row = cursor.fetchone()
        return row[0] if row else None

    def add_pricing(self, part_number: str, supplier: str, unit_price: float,
                   quantity_available: int, lead_time_days: int = 1,
                   supplier_part_number: str = None, quantity_breaks: Dict = None):
        """Add or update pricing for a part from a supplier"""
        part_id = self.get_part_id(part_number)
        if not part_id:
            logger.error(f"Part not found: {part_number}")
            return

        cursor = self.conn.cursor()
        qb_json = json.dumps(quantity_breaks or {})

        try:
            cursor.execute("""
                INSERT INTO pricing (part_id, supplier, supplier_part_number, unit_price,
                                    quantity_available, lead_time_days, quantity_breaks)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(part_id, supplier) DO UPDATE SET
                    unit_price = excluded.unit_price,
                    quantity_available = excluded.quantity_available,
                    lead_time_days = excluded.lead_time_days,
                    last_updated = CURRENT_TIMESTAMP
            """, (part_id, supplier, supplier_part_number, unit_price,
                  quantity_available, lead_time_days, qb_json))

            # Record price history
            cursor.execute("""
                INSERT INTO price_history (part_id, supplier, price, quantity_available)
                VALUES (?, ?, ?, ?)
            """, (part_id, supplier, unit_price, quantity_available))

            self.conn.commit()
        except Exception as e:
            logger.error(f"Failed to add pricing: {e}")

    def add_cross_reference(self, part_number: str, supplier: str,
                           supplier_part_number: str, manufacturer_part_number: str = None):
        """Add supplier part number cross-reference"""
        part_id = self.get_part_id(part_number)
        if not part_id:
            logger.error(f"Part not found: {part_number}")
            return

        cursor = self.conn.cursor()
        try:
            cursor.execute("""
                INSERT INTO cross_references (part_id, supplier, supplier_part_number,
                                            manufacturer_part_number)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(supplier, supplier_part_number) DO NOTHING
            """, (part_id, supplier, supplier_part_number, manufacturer_part_number))
            self.conn.commit()
        except Exception as e:
            logger.error(f"Failed to add cross-reference: {e}")

    def search_parts(self, query: str, category: str = None, limit: int = 50) -> List[Dict]:
        """Search parts by query string"""
        cursor = self.conn.cursor()

        query_lower = f"%{query.lower()}%"

        where_clause = """
            WHERE (part_number LIKE ? OR
                   description LIKE ? OR
                   manufacturer LIKE ?)
        """
        params = [query_lower, query_lower, query_lower]

        if category:
            where_clause += " AND category = ?"
            params.append(category)

        sql = f"""
            SELECT p.id, p.part_number, p.manufacturer, p.description, p.category,
                   p.specs, p.datasheet_url, p.rohs_compliant, p.packaging
            FROM parts p
            {where_clause}
            LIMIT ?
        """
        params.append(limit)

        cursor.execute(sql, params)
        rows = cursor.fetchall()

        results = []
        for row in rows:
            results.append({
                'id': row[0],
                'part_number': row[1],
                'manufacturer': row[2],
                'description': row[3],
                'category': row[4],
                'specs': json.loads(row[5]) if row[5] else {},
                'datasheet_url': row[6],
                'rohs_compliant': bool(row[7]),
                'packaging': row[8],
            })

        return results

    def get_part(self, part_number: str) -> Optional[Dict]:
        """Get full part details"""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT id, part_number, manufacturer, description, category, specs,
                   datasheet_url, rohs_compliant, packaging
            FROM parts WHERE part_number = ?
        """, (part_number,))

        row = cursor.fetchone()
        if not row:
            return None

        part_id = row[0]
        part = {
            'id': part_id,
            'part_number': row[1],
            'manufacturer': row[2],
            'description': row[3],
            'category': row[4],
            'specs': json.loads(row[5]) if row[5] else {},
            'datasheet_url': row[6],
            'rohs_compliant': bool(row[7]),
            'packaging': row[8],
            'suppliers': {}
        }

        # Get pricing from all suppliers
        cursor.execute("""
            SELECT supplier, supplier_part_number, unit_price, quantity_available,
                   lead_time_days, quantity_breaks
            FROM pricing WHERE part_id = ?
            ORDER BY unit_price ASC
        """, (part_id,))

        for row in cursor.fetchall():
            supplier = row[0]
            part['suppliers'][supplier] = {
                'supplier_part_number': row[1],
                'unit_price': row[2],
                'quantity_available': row[3],
                'lead_time_days': row[4],
                'quantity_breaks': json.loads(row[5]) if row[5] else {}
            }

        return part

    def get_prices(self, part_number: str) -> Dict[str, Dict]:
        """Get prices from all suppliers for a part"""
        cursor = self.conn.cursor()
        part_id = self.get_part_id(part_number)

        if not part_id:
            return {}

        cursor.execute("""
            SELECT supplier, unit_price, quantity_available, lead_time_days,
                   supplier_part_number
            FROM pricing WHERE part_id = ?
            ORDER BY unit_price ASC
        """, (part_id,))

        prices = {}
        for row in cursor.fetchall():
            prices[row[0]] = {
                'unit_price': row[1],
                'quantity_available': row[2],
                'lead_time_days': row[3],
                'supplier_part_number': row[4],
            }

        return prices

    def get_categories(self) -> List[str]:
        """Get all product categories"""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT DISTINCT category FROM parts
            WHERE category IS NOT NULL AND category != ''
            ORDER BY category
        """)
        return [row[0] for row in cursor.fetchall()]

    def get_stale_prices(self, hours: int = 24) -> List[Dict]:
        """Get parts with stale pricing (not updated in N hours)"""
        cursor = self.conn.cursor()

        since = datetime.utcnow() - timedelta(hours=hours)

        cursor.execute("""
            SELECT p.id, p.part_number, pr.supplier, pr.last_updated
            FROM parts p
            JOIN pricing pr ON p.id = pr.part_id
            WHERE pr.last_updated < ?
            ORDER BY pr.last_updated ASC
        """, (since,))

        stale = []
        for row in cursor.fetchall():
            stale.append({
                'part_id': row[0],
                'part_number': row[1],
                'supplier': row[2],
                'last_updated': row[3]
            })

        return stale

    def get_trending_parts(self, lookback_days: int = 7, limit: int = 20) -> List[Dict]:
        """Get trending parts (high search volume)"""
        since = datetime.utcnow() - timedelta(days=lookback_days)

        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT p.part_number, COUNT(*) as search_count
            FROM parts p
            JOIN search_index si ON p.id = si.part_id
            WHERE si.id IN (
                SELECT id FROM search_index
                WHERE recorded_at > ?
            )
            GROUP BY p.id
            ORDER BY search_count DESC
            LIMIT ?
        """, (since, limit))

        trending = [{'part_number': row[0], 'searches': row[1]} for row in cursor.fetchall()]
        return trending

    def get_price_history(self, part_number: str, supplier: str = None,
                         days: int = 30) -> List[Dict]:
        """Get price history for a part"""
        part_id = self.get_part_id(part_number)
        if not part_id:
            return []

        since = datetime.utcnow() - timedelta(days=days)

        cursor = self.conn.cursor()

        if supplier:
            cursor.execute("""
                SELECT supplier, price, quantity_available, recorded_at
                FROM price_history
                WHERE part_id = ? AND supplier = ? AND recorded_at > ?
                ORDER BY recorded_at ASC
            """, (part_id, supplier, since))
        else:
            cursor.execute("""
                SELECT supplier, price, quantity_available, recorded_at
                FROM price_history
                WHERE part_id = ? AND recorded_at > ?
                ORDER BY recorded_at ASC
            """, (part_id, since))

        history = []
        for row in cursor.fetchall():
            history.append({
                'supplier': row[0],
                'price': row[1],
                'quantity_available': row[2],
                'recorded_at': row[3]
            })

        return history

    def bulk_import_parts(self, parts: List[Dict]):
        """Import multiple parts efficiently"""
        cursor = self.conn.cursor()

        for part in parts:
            try:
                part_id = self.add_part(
                    part_number=part.get('part_number', ''),
                    manufacturer=part.get('manufacturer', ''),
                    description=part.get('description', ''),
                    category=part.get('category', ''),
                    specs=part.get('specs'),
                    datasheet_url=part.get('datasheet_url'),
                    rohs_compliant=part.get('rohs_compliant', False),
                    packaging=part.get('packaging', 'Individual')
                )

                # Add pricing for each supplier
                for supplier_data in part.get('suppliers', []):
                    self.add_pricing(
                        part_number=part['part_number'],
                        supplier=supplier_data.get('supplier', ''),
                        unit_price=supplier_data.get('unit_price', 0),
                        quantity_available=supplier_data.get('quantity_available', 0),
                        lead_time_days=supplier_data.get('lead_time_days', 1),
                        supplier_part_number=supplier_data.get('supplier_part_number'),
                        quantity_breaks=supplier_data.get('quantity_breaks')
                    )

            except Exception as e:
                logger.error(f"Failed to import part: {e}")

        self.conn.commit()
        logger.info(f"Imported {len(parts)} parts")

    def export_catalog(self, output_file: str = "catalog_export.json"):
        """Export entire catalog to JSON"""
        cursor = self.conn.cursor()
        cursor.execute("SELECT part_number FROM parts ORDER BY part_number")

        parts = []
        for row in cursor.fetchall():
            part = self.get_part(row[0])
            if part:
                parts.append(part)

        with open(output_file, 'w') as f:
            json.dump(parts, f, indent=2, default=str)

        logger.info(f"Exported {len(parts)} parts to {output_file}")
        return output_file
