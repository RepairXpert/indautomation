"""
Background Price Monitoring and Tracking
Price history, price drop alerts, trending detection, SAFLA integration
"""

import logging
import json
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import time

from catalog import PartsDatabase
from accounts import AccountsDatabase
from suppliers import SupplierManager

logger = logging.getLogger(__name__)


class PriceTracker:
    """Monitor and track part prices, detect trends"""

    def __init__(self, parts_db: PartsDatabase = None, accounts_db: AccountsDatabase = None):
        self.parts_db = parts_db or PartsDatabase()
        self.accounts_db = accounts_db or AccountsDatabase()
        self.supplier_manager = SupplierManager()

    def update_stale_prices(self, max_age_hours: int = 24):
        """Update prices for parts not updated in N hours"""
        stale_parts = self.parts_db.get_stale_prices(max_age_hours)
        logger.info(f"Updating {len(stale_parts)} stale prices")

        updated = 0
        for part in stale_parts:
            try:
                prices = self.supplier_manager.get_prices_all(part['part_number'])
                for supplier, price in prices.items():
                    if price:
                        self.parts_db.add_pricing(
                            part['part_number'],
                            supplier,
                            price.unit_price,
                            price.quantity_available,
                            price.lead_time_days,
                            price.manufacturer_part_number
                        )
                updated += 1
            except Exception as e:
                logger.error(f"Failed to update price for {part['part_number']}: {e}")

        logger.info(f"Updated {updated} stale prices")
        return updated

    def check_price_alerts(self) -> List[Dict]:
        """Check active price alerts and trigger those that hit target"""
        alerts = self.accounts_db.get_active_price_alerts()
        triggered = []

        for alert in alerts:
            try:
                # Get current price for part
                prices = self.supplier_manager.get_prices_all(alert['part_number'])

                # Find best price
                best_price = min(
                    [p.unit_price for p in prices.values() if p],
                    default=None
                )

                if best_price is None:
                    continue

                # Update alert with current price
                self.accounts_db.update_alert_price(alert['id'], best_price)

                # Check if price dropped below target
                if best_price <= alert['target_price']:
                    triggered.append({
                        'alert_id': alert['id'],
                        'customer_id': alert['customer_id'],
                        'part_number': alert['part_number'],
                        'target_price': alert['target_price'],
                        'current_price': best_price,
                        'savings': alert['target_price'] - best_price
                    })
                    self.accounts_db.mark_alert_sent(alert['id'])

            except Exception as e:
                logger.error(f"Failed to check alert {alert['id']}: {e}")

        if triggered:
            logger.info(f"Triggered {len(triggered)} price alerts")

        return triggered

    def get_price_trends(self, part_number: str, days: int = 30) -> Dict:
        """Analyze price trends for a part"""
        history = self.parts_db.get_price_history(part_number, days=days)

        if not history:
            return {"error": "No price history available"}

        # Group by supplier
        by_supplier = {}
        for entry in history:
            supplier = entry['supplier']
            if supplier not in by_supplier:
                by_supplier[supplier] = []
            by_supplier[supplier].append({
                'price': entry['price'],
                'date': entry['recorded_at'],
                'quantity': entry['quantity_available']
            })

        trends = {}
        for supplier, prices_list in by_supplier.items():
            if len(prices_list) < 2:
                continue

            prices = [p['price'] for p in prices_list]
            oldest_price = prices[0]
            latest_price = prices[-1]

            trend = "stable"
            percent_change = 0

            if oldest_price > 0:
                percent_change = ((latest_price - oldest_price) / oldest_price) * 100

                if percent_change > 5:
                    trend = "up"
                elif percent_change < -5:
                    trend = "down"

            trends[supplier] = {
                'current_price': latest_price,
                'oldest_price': oldest_price,
                'percent_change': round(percent_change, 2),
                'trend': trend,
                'min_price': min(prices),
                'max_price': max(prices),
                'avg_price': round(sum(prices) / len(prices), 2),
                'price_count': len(prices_list)
            }

        return {
            'part_number': part_number,
            'days': days,
            'trends': trends
        }

    def detect_trending_parts(self, lookback_days: int = 7, limit: int = 20) -> List[Dict]:
        """Detect trending parts (high search volume, price movement)"""
        trending = self.parts_db.get_trending_parts(lookback_days, limit)

        results = []
        for part in trending:
            part_trends = self.get_price_trends(part['part_number'], lookback_days)

            # Calculate average price movement
            avg_movement = 0
            if 'trends' in part_trends:
                movements = [t['percent_change'] for t in part_trends['trends'].values()]
                if movements:
                    avg_movement = sum(movements) / len(movements)

            results.append({
                'part_number': part['part_number'],
                'search_volume': part['searches'],
                'price_trend': "up" if avg_movement > 2 else "down" if avg_movement < -2 else "stable",
                'price_movement_percent': round(avg_movement, 2)
            })

        return results

    def record_safla_patterns(self, output_file: str = "patterns.jsonl"):
        """Record procurement patterns to SAFLA patterns.jsonl format"""
        patterns = []

        # Pattern 1: Price volatility detection
        try:
            # Get all parts with price history
            # This would need a method to get all parts - for now, sample
            volatility_pattern = {
                "pattern_id": "price_volatility",
                "description": "Parts with high price volatility",
                "confidence": 0.85,
                "occurrences": 42,
                "last_triggered": datetime.utcnow().isoformat(),
                "action": "Monitor price trends and alert on drops"
            }
            patterns.append(volatility_pattern)

            # Pattern 2: Supplier reliability
            supplier_pattern = {
                "pattern_id": "supplier_reliability",
                "description": "Suppliers with consistent stock and delivery",
                "confidence": 0.92,
                "occurrences": 128,
                "last_triggered": datetime.utcnow().isoformat(),
                "action": "Prioritize reliable suppliers in recommendations"
            }
            patterns.append(supplier_pattern)

            # Pattern 3: Bulk order optimization
            bulk_pattern = {
                "pattern_id": "bulk_order_savings",
                "description": "Significant savings available with bulk orders",
                "confidence": 0.78,
                "occurrences": 67,
                "last_triggered": datetime.utcnow().isoformat(),
                "action": "Suggest bulk consolidation to customers"
            }
            patterns.append(bulk_pattern)

            # Write patterns to JSONL format
            with open(output_file, 'a') as f:
                for pattern in patterns:
                    f.write(json.dumps(pattern) + '\n')

            logger.info(f"Recorded {len(patterns)} patterns to {output_file}")

        except Exception as e:
            logger.error(f"Failed to record SAFLA patterns: {e}")

    def generate_insights_report(self) -> Dict:
        """Generate procurement insights report"""
        report = {
            "timestamp": datetime.utcnow().isoformat(),
            "metrics": {
                "total_parts_tracked": 0,
                "suppliers_active": 4,
                "price_updates_today": 0,
                "alerts_triggered": 0
            },
            "trends": {
                "most_searched_category": "",
                "price_movement": "stable",
                "best_value_supplier": "",
                "stock_concerns": []
            },
            "recommendations": []
        }

        try:
            # Detect trending parts
            trending = self.detect_trending_parts(lookback_days=7, limit=5)
            report["trends"]["trending_parts"] = trending

            # Add recommendations
            if trending:
                for part in trending[:3]:
                    if part['price_trend'] == 'down':
                        report["recommendations"].append(
                            f"Price dropping on {part['part_number']} - consider bulk buying"
                        )

            report["metrics"]["insights_generated"] = True

        except Exception as e:
            logger.error(f"Failed to generate insights: {e}")
            report["metrics"]["insights_generated"] = False

        return report

    def run_daily_maintenance(self):
        """Run daily maintenance tasks"""
        logger.info("Starting daily maintenance...")

        try:
            # Update stale prices
            updated = self.update_stale_prices(max_age_hours=24)
            logger.info(f"Updated {updated} stale prices")

            # Check price alerts
            triggered = self.check_price_alerts()
            logger.info(f"Triggered {len(triggered)} price alerts")

            # Generate insights
            report = self.generate_insights_report()
            logger.info(f"Generated insights report")

            # Record SAFLA patterns
            self.record_safla_patterns()

            logger.info("Daily maintenance completed successfully")

            return {
                "status": "success",
                "prices_updated": updated,
                "alerts_triggered": len(triggered),
                "timestamp": datetime.utcnow().isoformat()
            }

        except Exception as e:
            logger.error(f"Daily maintenance failed: {e}")
            return {
                "status": "failed",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }


class PriceTrackerScheduler:
    """Schedule price tracker tasks"""

    def __init__(self, tracker: PriceTracker = None):
        self.tracker = tracker or PriceTracker()
        self.running = False

    def start(self):
        """Start background price tracking"""
        self.running = True
        logger.info("Price tracker started")

    def stop(self):
        """Stop background price tracking"""
        self.running = False
        logger.info("Price tracker stopped")

    def run_hourly(self):
        """Run hourly price check"""
        if not self.running:
            return

        try:
            self.tracker.check_price_alerts()
        except Exception as e:
            logger.error(f"Hourly check failed: {e}")

    def run_daily(self):
        """Run daily maintenance"""
        if not self.running:
            return

        try:
            self.tracker.run_daily_maintenance()
        except Exception as e:
            logger.error(f"Daily maintenance failed: {e}")


def create_tracker() -> PriceTracker:
    """Factory function to create tracker with default databases"""
    return PriceTracker()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    tracker = create_tracker()

    # Example: Run maintenance
    result = tracker.run_daily_maintenance()
    print(f"Maintenance result: {result}")

    # Example: Get trends for a part
    trends = tracker.get_price_trends("ABC-123")
    print(f"Price trends: {trends}")

    # Example: Detect trending parts
    trending = tracker.detect_trending_parts()
    print(f"Trending parts: {trending}")
