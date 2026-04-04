"""
Price Comparison and Optimization Engine
Analyzes prices across suppliers, factors in shipping/margins, calculates best value
"""

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime
from enum import Enum

from .suppliers import PartPrice, BaseSupplier, SupplierManager

logger = logging.getLogger(__name__)


class AccountTier(Enum):
    """Customer account tiers"""
    FREE = "free"
    PRO = "pro"
    ENTERPRISE = "enterprise"


@dataclass
class ShippingInfo:
    """Shipping cost and timeline info"""
    cost: float
    days: int
    carrier: str = "Standard"
    expedited_cost: Optional[float] = None
    expedited_days: Optional[int] = None


@dataclass
class SupplierAccount:
    """Customer's account with a supplier"""
    supplier: str
    account_number: str
    discount_percent: float = 0.0
    negotiated_pricing: Dict[str, float] = None  # part_number -> price
    is_active: bool = True


@dataclass
class PricingQuote:
    """Quote for a single part from a supplier"""
    supplier: str
    part_number: str
    unit_price: float
    quantity: int
    total_cost: float
    shipping: float
    lead_time_days: int
    stock_available: int
    in_stock: bool
    account_discount: float = 0
    notes: str = ""


@dataclass
class BestPriceRecommendation:
    """Best pricing recommendation for a part"""
    part_number: str
    best_supplier: str
    unit_price: float
    total_cost: float  # including shipping
    shipping: float
    lead_time_days: int
    alternatives: List[PricingQuote]
    value_score: float
    cost_savings: float  # vs. second best
    timestamp: datetime = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow()


class ShippingCalculator:
    """Calculate shipping costs by supplier and destination"""

    # Base shipping by supplier
    SHIPPING_MATRIX = {
        "digikey": {
            "base": 10.0,
            "free_over": 100.0,
            "standard_days": 3,
            "expedited": 25.0,
            "expedited_days": 1
        },
        "mouser": {
            "base": 8.0,
            "free_over": 75.0,
            "standard_days": 3,
            "expedited": 20.0,
            "expedited_days": 1
        },
        "automation_direct": {
            "base": 12.0,
            "free_over": 150.0,
            "standard_days": 2,
            "expedited": 35.0,
            "expedited_days": 1
        },
        "amazon": {
            "base": 0.0,  # Prime eligible usually
            "free_over": 0.0,
            "standard_days": 2,
            "expedited": 0.0,
            "expedited_days": 1
        }
    }

    @classmethod
    def calculate(cls, supplier: str, order_subtotal: float,
                  expedited: bool = False) -> ShippingInfo:
        """Calculate shipping cost and time"""
        config = cls.SHIPPING_MATRIX.get(supplier, {})

        if expedited:
            cost = config.get("expedited", 0)
            days = config.get("expedited_days", 2)
        else:
            cost = config.get("base", 0)
            free_over = config.get("free_over", float('inf'))
            if order_subtotal >= free_over:
                cost = 0

            days = config.get("standard_days", 3)

        return ShippingInfo(
            cost=cost,
            days=days,
            carrier="Standard" if not expedited else "Expedited"
        )


class PriceOptimizer:
    """Optimize pricing based on various factors"""

    def __init__(self, supplier_manager: SupplierManager):
        self.supplier_manager = supplier_manager
        self.shipping_calc = ShippingCalculator()

    def calculate_best_value(
        self,
        quotes: Dict[str, PricingQuote],
        weight_price: float = 0.4,
        weight_availability: float = 0.3,
        weight_lead_time: float = 0.2,
        weight_reliability: float = 0.1
    ) -> float:
        """
        Calculate composite value score for a supplier
        Higher score = better value
        """
        if not quotes:
            return 0.0

        # Normalize scores 0-100
        price_scores = []
        availability_scores = []
        lead_time_scores = []

        for quote in quotes.values():
            # Price: lower is better (normalized to 100)
            price_scores.append(quote.unit_price)
            # Availability: 100 if in stock, 50 if partial, 0 if out
            avail_score = 100 if quote.in_stock else (50 if quote.stock_available > 0 else 0)
            availability_scores.append(avail_score)
            # Lead time: shorter is better (normalized to 100)
            lead_time_scores.append(quote.lead_time_days)

        min_price = min(price_scores)
        max_price = max(price_scores)
        price_range = max_price - min_price or 1
        price_normalized = [(min_price + (max_price - p) / price_range * 100) for p in price_scores]

        max_lead_time = max(lead_time_scores)
        lead_time_normalized = [(max_lead_time - lt) / max_lead_time * 100 for lt in lead_time_scores]

        avg_scores = []
        for i, quote in enumerate(quotes.values()):
            score = (
                price_normalized[i] * weight_price +
                availability_scores[i] * weight_availability +
                lead_time_normalized[i] * weight_lead_time +
                100 * weight_reliability  # Assume all equal reliability
            )
            avg_scores.append(score)

        return max(avg_scores) if avg_scores else 0

    def apply_account_discount(self, quote: PricingQuote,
                              account: Optional[SupplierAccount]) -> PricingQuote:
        """Apply customer account discount if available"""
        if not account:
            return quote

        # Check for negotiated pricing first
        if account.negotiated_pricing:
            negotiated = account.negotiated_pricing.get(quote.part_number)
            if negotiated:
                original_total = quote.unit_price * quote.quantity
                new_total = negotiated * quote.quantity + quote.shipping
                quote.account_discount = original_total - (new_total - quote.shipping)
                quote.unit_price = negotiated
                quote.total_cost = new_total

        # Fall back to percentage discount
        elif account.discount_percent > 0:
            discount_amount = quote.unit_price * (account.discount_percent / 100)
            quote.unit_price -= discount_amount
            quote.total_cost = quote.unit_price * quote.quantity + quote.shipping
            quote.account_discount = discount_amount * quote.quantity

        return quote

    def compare_suppliers(
        self,
        part_number: str,
        quantity: int = 1,
        prices: Dict[str, Optional[PartPrice]] = None,
        customer_accounts: Dict[str, SupplierAccount] = None
    ) -> List[PricingQuote]:
        """Compare prices across all suppliers"""

        if prices is None:
            prices = self.supplier_manager.get_prices_all(part_number)

        if customer_accounts is None:
            customer_accounts = {}

        quotes = []

        for supplier_name, price in prices.items():
            if price is None:
                continue

            # Calculate shipping
            subtotal = price.unit_price * quantity
            shipping = self.shipping_calc.calculate(supplier_name, subtotal)

            quote = PricingQuote(
                supplier=supplier_name,
                part_number=part_number,
                unit_price=price.unit_price,
                quantity=quantity,
                total_cost=subtotal + shipping.cost,
                shipping=shipping.cost,
                lead_time_days=price.lead_time_days + shipping.days,
                stock_available=price.quantity_available,
                in_stock=price.quantity_available >= quantity,
                notes=f"Lead time: {price.lead_time_days}d, Stock: {price.quantity_available}"
            )

            # Apply account discount if available
            account = customer_accounts.get(supplier_name)
            if account:
                quote = self.apply_account_discount(quote, account)

            quotes.append(quote)

        # Sort by total cost
        quotes.sort(key=lambda q: q.total_cost)
        return quotes

    def get_best_price(
        self,
        part_number: str,
        quantity: int = 1,
        prices: Dict[str, Optional[PartPrice]] = None,
        customer_accounts: Dict[str, SupplierAccount] = None
    ) -> Optional[BestPriceRecommendation]:
        """Get best price recommendation for a part"""

        quotes = self.compare_suppliers(
            part_number,
            quantity,
            prices,
            customer_accounts
        )

        if not quotes:
            return None

        best = quotes[0]
        second_best = quotes[1] if len(quotes) > 1 else None
        cost_savings = 0

        if second_best:
            cost_savings = second_best.total_cost - best.total_cost

        return BestPriceRecommendation(
            part_number=part_number,
            best_supplier=best.supplier,
            unit_price=best.unit_price,
            total_cost=best.total_cost,
            shipping=best.shipping,
            lead_time_days=best.lead_time_days,
            alternatives=quotes[1:],
            value_score=self.calculate_best_value({best.supplier: best}),
            cost_savings=cost_savings
        )

    def optimize_bulk_order(
        self,
        parts: Dict[str, int],  # part_number -> quantity
        prices: Dict[str, Dict[str, Optional[PartPrice]]] = None,
        customer_accounts: Dict[str, SupplierAccount] = None,
        max_suppliers: int = 3
    ) -> Dict[str, List[Tuple[str, int]]]:
        """
        Optimize bulk order across multiple parts and suppliers.
        Returns: {part_number: [(supplier, quantity), ...]}
        """

        if prices is None:
            prices = {}
            for part_num in parts.keys():
                prices[part_num] = self.supplier_manager.get_prices_all(part_num)

        allocation = {}

        for part_num, quantity in parts.items():
            quotes = self.compare_suppliers(
                part_num,
                quantity,
                prices.get(part_num),
                customer_accounts
            )

            if not quotes:
                continue

            # For now, simple strategy: use best supplier for each part
            # In production, could implement more complex bin packing
            best_quote = quotes[0]
            allocation[part_num] = [(best_quote.supplier, quantity)]

        return allocation


class ResaleMarginCalculator:
    """Calculate resale pricing with margins"""

    def __init__(self, default_margin_percent: float = 20.0):
        self.default_margin_percent = default_margin_percent
        # Category-specific margins (higher for slower-moving items)
        self.category_margins = {
            "connectors": 15,
            "switches": 18,
            "sensors": 25,
            "motors": 12,
            "drives": 15,
            "plc_modules": 20,
            "cables": 20,
            "fasteners": 25,
        }

    def calculate_resale_price(
        self,
        cost_per_unit: float,
        category: str = None,
        margin_override: float = None
    ) -> float:
        """Calculate resale price from cost"""

        if margin_override is not None:
            margin = margin_override
        elif category and category.lower() in self.category_margins:
            margin = self.category_margins[category.lower()]
        else:
            margin = self.default_margin_percent

        return cost_per_unit * (1 + margin / 100)

    def calculate_margin_dollars(
        self,
        cost_per_unit: float,
        resale_price: float,
        quantity: int = 1
    ) -> float:
        """Calculate margin dollars"""
        return (resale_price - cost_per_unit) * quantity

    def calculate_margin_percent(
        self,
        cost_per_unit: float,
        resale_price: float
    ) -> float:
        """Calculate margin percentage"""
        if cost_per_unit == 0:
            return 0
        return ((resale_price - cost_per_unit) / resale_price) * 100


class PriceComparator:
    """High-level price comparison interface"""

    def __init__(self):
        self.supplier_manager = SupplierManager()
        self.optimizer = PriceOptimizer(self.supplier_manager)
        self.margin_calc = ResaleMarginCalculator()

    def get_comparison_table(
        self,
        part_number: str,
        quantity: int = 1
    ) -> Dict[str, Any]:
        """Get formatted comparison table for UI"""

        quotes = self.optimizer.compare_suppliers(part_number, quantity)

        table_data = []
        for quote in quotes:
            table_data.append({
                'supplier': quote.supplier,
                'unit_price': f"${quote.unit_price:.2f}",
                'quantity': quantity,
                'subtotal': f"${quote.unit_price * quantity:.2f}",
                'shipping': f"${quote.shipping:.2f}",
                'total': f"${quote.total_cost:.2f}",
                'lead_time': f"{quote.lead_time_days}d",
                'stock': quote.stock_available,
                'in_stock': 'Yes' if quote.in_stock else 'No',
            })

        return {
            'part_number': part_number,
            'quantity': quantity,
            'quotes': table_data,
            'best_supplier': quotes[0].supplier if quotes else None,
            'best_price': f"${quotes[0].total_cost:.2f}" if quotes else None,
        }
