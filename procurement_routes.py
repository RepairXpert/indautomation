
# ============================================================================
# Procurement Engine API Routes (mounted at /api/procurement)
# ============================================================================

from fastapi import APIRouter
import sys
import os

# Add procurement module path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'procurement'))

from procurement.catalog import PartsDatabase
from procurement.accounts import AccountsDatabase
from procurement.price_engine import PriceComparator, ResaleMarginCalculator
from procurement.suppliers import SupplierManager

procurement_router = APIRouter(prefix="/api/procurement", tags=["procurement"])

_parts_db = None
_accounts_db = None
_price_comparator = None

def _get_parts_db():
    global _parts_db
    if _parts_db is None:
        _parts_db = PartsDatabase(os.path.join(os.path.dirname(__file__), 'procurement', 'parts_catalog.db'))
    return _parts_db

def _get_accounts_db():
    global _accounts_db
    if _accounts_db is None:
        _accounts_db = AccountsDatabase(os.path.join(os.path.dirname(__file__), 'procurement', 'accounts.db'))
    return _accounts_db

@procurement_router.get("/health")
async def procurement_health():
    return {"status": "ok", "engine": "procurement", "version": "1.0.0"}

@procurement_router.get("/parts/search")
async def search_parts(q: str, category: str = None, limit: int = 50):
    db = _get_parts_db()
    results = db.search_parts(q, limit=limit)
    return {"query": q, "count": len(results), "parts": results}

@procurement_router.get("/parts/{part_number}/compare")
async def compare_prices(part_number: str, quantity: int = 1):
    db = _get_parts_db()
    part = db.get_part(part_number)
    if not part:
        return {"error": "Part not found", "part_number": part_number}
    prices = db.get_prices(part_number)
    # Normalize to list format
    suppliers = [
        {"supplier": sup, **data}
        for sup, data in prices.items()
    ]
    return {"part_number": part_number, "quantity": quantity, "suppliers": suppliers}

@procurement_router.get("/parts/{part_number}/best-price")
async def best_price(part_number: str, quantity: int = 1):
    db = _get_parts_db()
    part = db.get_part(part_number)
    if not part:
        return {"error": "Part not found", "part_number": part_number}
    prices = db.get_prices(part_number)
    if not prices:
        return {"error": "No pricing available", "part_number": part_number}

    # prices is a dict: {supplier: {unit_price, quantity_available, lead_time_days, ...}}
    suppliers = [
        {"supplier": sup, **data}
        for sup, data in prices.items()
    ]
    sorted_suppliers = sorted(suppliers, key=lambda p: p.get('unit_price', float('inf')))
    best = sorted_suppliers[0]
    second_price = sorted_suppliers[1]['unit_price'] if len(sorted_suppliers) > 1 else best['unit_price']

    return {
        "part_number": part_number,
        "best_supplier": best['supplier'],
        "unit_price": best['unit_price'],
        "total_cost": round(best['unit_price'] * quantity, 2),
        "shipping": 0,
        "lead_time_days": best.get('lead_time_days', 3),
        "in_stock": best.get('quantity_available', 0) > 0,
        "cost_savings": round(second_price - best['unit_price'], 2) if second_price > best['unit_price'] else 0,
        "alternatives": sorted_suppliers[1:],
        "quantity": quantity
    }

@procurement_router.get("/catalog/categories")
async def list_categories():
    db = _get_parts_db()
    return {"categories": db.get_categories()}

@procurement_router.get("/catalog/trending")
async def trending_parts():
    from procurement.price_tracker import PriceTracker
    tracker = PriceTracker(_get_parts_db())
    return {"trending": tracker.detect_trending_parts(limit=10)}

@procurement_router.get("/dashboard")
async def procurement_dashboard():
    from fastapi.responses import FileResponse
    dashboard_path = os.path.join(os.path.dirname(__file__), 'procurement', 'dashboard.html')
    return FileResponse(dashboard_path, media_type='text/html')
