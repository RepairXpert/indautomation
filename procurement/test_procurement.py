"""
Unit tests for Procurement Engine
"""

import pytest
import tempfile
import os
from datetime import datetime, timedelta

from catalog import PartsDatabase, PartPrice
from accounts import AccountsDatabase, AccountTier
from price_engine import (
    PriceComparator, ResaleMarginCalculator, ShippingCalculator,
    PricingQuote, BestPriceRecommendation
)
from suppliers import (
    SupplierManager, AutomationDirectSupplier, SupplierCache,
    PartPrice, PartDetails
)
from price_tracker import PriceTracker


class TestPartsDatabase:
    """Tests for parts catalog database"""

    @pytest.fixture
    def db(self):
        """Create temporary database for testing"""
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        db = PartsDatabase(path)
        yield db
        db.close()
        os.unlink(path)

    def test_add_part(self, db):
        """Test adding a part"""
        part_id = db.add_part(
            part_number="TEST-123",
            manufacturer="TestMfg",
            description="Test Part",
            category="Test"
        )
        assert part_id > 0

    def test_get_part(self, db):
        """Test retrieving a part"""
        db.add_part("TEST-456", "Mfg", "Part", "Cat")
        part = db.get_part("TEST-456")

        assert part is not None
        assert part['part_number'] == "TEST-456"
        assert part['manufacturer'] == "Mfg"

    def test_search_parts(self, db):
        """Test part search"""
        db.add_part("MOTOR-1HP", "WEG", "1 HP Motor", "Motors")
        db.add_part("MOTOR-2HP", "WEG", "2 HP Motor", "Motors")
        db.add_part("VFD-3HP", "ABB", "3 HP Drive", "VFDs")

        results = db.search_parts("MOTOR")
        assert len(results) == 2

        results = db.search_parts("motor", category="Motors")
        assert len(results) == 2

    def test_add_pricing(self, db):
        """Test adding pricing"""
        db.add_part("TEST-789", "Mfg", "Part", "Cat")
        db.add_pricing("TEST-789", "supplier_a", 100.00, 50, 2)

        prices = db.get_prices("TEST-789")
        assert "supplier_a" in prices
        assert prices["supplier_a"]["unit_price"] == 100.00

    def test_get_categories(self, db):
        """Test getting categories"""
        db.add_part("PART-1", "Mfg", "Part 1", "Motors")
        db.add_part("PART-2", "Mfg", "Part 2", "Sensors")
        db.add_part("PART-3", "Mfg", "Part 3", "Motors")

        categories = db.get_categories()
        assert "Motors" in categories
        assert "Sensors" in categories

    def test_bulk_import(self, db):
        """Test bulk import"""
        parts = [
            {
                'part_number': 'BULK-1',
                'manufacturer': 'Mfg',
                'description': 'Part 1',
                'category': 'Cat',
                'suppliers': [
                    {'supplier': 'sup_a', 'unit_price': 100, 'quantity_available': 50}
                ]
            },
            {
                'part_number': 'BULK-2',
                'manufacturer': 'Mfg',
                'description': 'Part 2',
                'category': 'Cat',
                'suppliers': [
                    {'supplier': 'sup_b', 'unit_price': 200, 'quantity_available': 30}
                ]
            }
        ]

        db.bulk_import_parts(parts)

        assert db.get_part("BULK-1") is not None
        assert db.get_part("BULK-2") is not None


class TestAccountsDatabase:
    """Tests for accounts database"""

    @pytest.fixture
    def db(self):
        """Create temporary database for testing"""
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        db = AccountsDatabase(path)
        yield db
        db.close()
        os.unlink(path)

    def test_create_customer(self, db):
        """Test creating customer"""
        customer_id = db.create_customer(
            email="test@example.com",
            company_name="Test Co",
            account_tier="pro"
        )
        assert customer_id > 0

    def test_get_customer(self, db):
        """Test retrieving customer"""
        customer_id = db.create_customer("user@example.com", "Company", "pro")
        customer = db.get_customer(customer_id)

        assert customer is not None
        assert customer['email'] == "user@example.com"
        assert customer['account_tier'] == "pro"

    def test_upgrade_account(self, db):
        """Test account upgrade"""
        customer_id = db.create_customer("user@example.com", "Company", "free")
        db.upgrade_account(customer_id, "pro")

        customer = db.get_customer(customer_id)
        assert customer['account_tier'] == "pro"
        assert customer['lookup_limit'] == 1000

    def test_check_lookup_limit(self, db):
        """Test lookup limit checking"""
        customer_id = db.create_customer("user@example.com", "Company", "free")

        # Should have limit
        assert db.check_lookup_limit(customer_id)

        # Increment to limit
        for _ in range(3):
            db.increment_lookup_count(customer_id)

        # Should be at limit
        assert not db.check_lookup_limit(customer_id)

    def test_supplier_accounts(self, db):
        """Test supplier account linking"""
        customer_id = db.create_customer("user@example.com", "Company")

        account_id = db.add_supplier_account(
            customer_id,
            "automation_direct",
            account_number="AD-123",
            discount_percent=15.0
        )

        assert account_id > 0

        accounts = db.get_supplier_accounts(customer_id)
        assert len(accounts) == 1
        assert accounts[0]['discount_percent'] == 15.0

    def test_price_alerts(self, db):
        """Test price alert creation"""
        customer_id = db.create_customer("user@example.com", "Company")

        alert_id = db.create_price_alert(customer_id, "PART-123", 100.00)
        assert alert_id > 0

        alerts = db.get_active_price_alerts()
        assert len(alerts) > 0

    def test_order_history(self, db):
        """Test order recording"""
        customer_id = db.create_customer("user@example.com", "Company")

        order_id = db.record_order(
            customer_id,
            parts=[{"part_number": "PART-1", "quantity": 5}],
            total_cost=500.00,
            supplier="automation_direct"
        )

        assert order_id > 0

        orders = db.get_order_history(customer_id)
        assert len(orders) == 1
        assert orders[0]['total_cost'] == 500.00


class TestPriceEngine:
    """Tests for price comparison engine"""

    def test_shipping_calculator(self):
        """Test shipping cost calculation"""
        shipping = ShippingCalculator.calculate("automation_direct", 150.0)
        assert shipping.cost == 0  # Free over $150

        shipping = ShippingCalculator.calculate("automation_direct", 50.0)
        assert shipping.cost == 12.0

    def test_resale_margin_calculator(self):
        """Test resale pricing"""
        calc = ResaleMarginCalculator(default_margin_percent=20)

        resale = calc.calculate_resale_price(100.0)
        assert resale == 120.0

        margin = calc.calculate_margin_percent(100.0, 120.0)
        assert margin == pytest.approx(16.67, 0.1)

    def test_resale_category_margin(self):
        """Test category-specific margins"""
        calc = ResaleMarginCalculator()

        resale = calc.calculate_resale_price(100.0, category="connectors")
        assert resale == pytest.approx(115.0, 0.1)

        resale = calc.calculate_resale_price(100.0, category="motors")
        assert resale == pytest.approx(112.0, 0.1)


class TestSupplierCache:
    """Tests for supplier caching"""

    def test_cache_set_get(self):
        """Test cache operations"""
        cache = SupplierCache()

        cache.set("key1", "value1")
        value = cache.get("key1", ttl_seconds=3600)
        assert value == "value1"

    def test_cache_ttl_expiry(self):
        """Test cache TTL expiry"""
        cache = SupplierCache()

        cache.set("key1", "value1")
        value = cache.get("key1", ttl_seconds=0)  # Already expired
        assert value is None

    def test_cache_clear(self):
        """Test cache clearing"""
        cache = SupplierCache()

        cache.set("key1", "value1")
        cache.clear()
        value = cache.get("key1", ttl_seconds=3600)
        assert value is None


class TestAutomationDirectSupplier:
    """Tests for AutomationDirect supplier"""

    @pytest.fixture
    def supplier(self):
        """Create supplier instance"""
        return AutomationDirectSupplier()

    def test_search_empty_catalog(self, supplier):
        """Test search with empty catalog"""
        results = supplier.search("VFD")
        assert results == []

    def test_import_and_search(self, supplier):
        """Test importing parts and searching"""
        parts = [
            {
                'part_number': 'PART-001',
                'description': 'Test Part 1',
                'manufacturer': 'TestMfg',
                'category': 'Test',
                'price': 100.0,
                'stock': 50
            }
        ]

        supplier.import_parts(parts)
        results = supplier.search("test")
        assert len(results) == 1

    def test_get_price(self, supplier):
        """Test price retrieval"""
        parts = [
            {
                'part_number': 'PART-002',
                'price': 250.0,
                'stock': 30,
                'lead_time': 2
            }
        ]

        supplier.import_parts(parts)
        price = supplier.get_price("PART-002")

        assert price is not None
        assert price.unit_price == 250.0
        assert price.quantity_available == 30


class TestPriceTracker:
    """Tests for price tracking"""

    @pytest.fixture
    def tracker(self):
        """Create tracker with temp databases"""
        fd_parts, parts_path = tempfile.mkstemp(suffix=".db")
        fd_accts, accts_path = tempfile.mkstemp(suffix=".db")
        os.close(fd_parts)
        os.close(fd_accts)

        parts_db = PartsDatabase(parts_path)
        accounts_db = AccountsDatabase(accts_path)

        tracker = PriceTracker(parts_db, accounts_db)
        yield tracker

        parts_db.close()
        accounts_db.close()
        os.unlink(parts_path)
        os.unlink(accts_path)

    def test_detect_trending_parts(self, tracker):
        """Test trending parts detection"""
        trending = tracker.detect_trending_parts(limit=5)
        assert isinstance(trending, list)

    def test_price_trends(self, tracker):
        """Test price trend analysis"""
        trends = tracker.get_price_trends("NONEXISTENT")
        assert 'error' in trends

    def test_generate_insights_report(self, tracker):
        """Test insights report generation"""
        report = tracker.generate_insights_report()

        assert 'timestamp' in report
        assert 'metrics' in report
        assert 'trends' in report


# Integration tests
class TestIntegration:
    """Integration tests across components"""

    @pytest.fixture
    def setup(self):
        """Setup test databases"""
        fd_parts, parts_path = tempfile.mkstemp(suffix=".db")
        fd_accts, accts_path = tempfile.mkstemp(suffix=".db")
        os.close(fd_parts)
        os.close(fd_accts)

        parts_db = PartsDatabase(parts_path)
        accounts_db = AccountsDatabase(accts_path)

        yield {
            'parts_db': parts_db,
            'accounts_db': accounts_db,
            'parts_path': parts_path,
            'accts_path': accts_path
        }

        parts_db.close()
        accounts_db.close()
        os.unlink(parts_path)
        os.unlink(accts_path)

    def test_end_to_end_quote(self, setup):
        """Test end-to-end quote generation"""
        parts_db = setup['parts_db']
        accounts_db = setup['accounts_db']

        # Add parts
        parts_db.add_part("PART-A", "Mfg", "Test Part A", "Test")
        parts_db.add_pricing("PART-A", "supplier_1", 100.0, 50, 2)
        parts_db.add_pricing("PART-A", "supplier_2", 105.0, 40, 1)

        # Create customer
        customer_id = accounts_db.create_customer("test@example.com", "Company")

        # Get prices
        prices = parts_db.get_prices("PART-A")
        assert len(prices) == 2

        # Verify best price is supplier_1
        best_price = min(p['unit_price'] for p in prices.values())
        assert best_price == 100.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
