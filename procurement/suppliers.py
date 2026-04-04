"""
Supplier Integration Layer
Abstracts multiple supplier APIs: DigiKey, Mouser, AutomationDirect, Amazon
"""

import os
import json
import logging
import hashlib
import time
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, asdict
from enum import Enum
import requests
from functools import wraps

logger = logging.getLogger(__name__)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('procurement.log'),
        logging.StreamHandler()
    ]
)


class SupplierName(Enum):
    """Supplier identifiers"""
    DIGIKEY = "digikey"
    MOUSER = "mouser"
    AUTOMATION_DIRECT = "automation_direct"
    AMAZON = "amazon"


@dataclass
class PartPrice:
    """Price data for a part from a supplier"""
    supplier: str
    part_number: str
    manufacturer_part_number: Optional[str]
    price: float
    quantity_available: int
    lead_time_days: int
    currency: str = "USD"
    unit_price: float = None
    quantity_breaks: Dict[int, float] = None  # {qty: price}
    timestamp: datetime = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow()
        if self.unit_price is None:
            self.unit_price = self.price

    def to_dict(self):
        data = asdict(self)
        data['timestamp'] = self.timestamp.isoformat()
        return data


@dataclass
class PartDetails:
    """Detailed part information"""
    supplier: str
    part_number: str
    manufacturer_part_number: Optional[str]
    manufacturer: str
    description: str
    category: str
    datasheet_url: Optional[str]
    specs: Dict[str, Any]
    rohs_compliant: bool
    packaging: str
    timestamp: datetime = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow()

    def to_dict(self):
        data = asdict(self)
        data['timestamp'] = self.timestamp.isoformat()
        return data


class RateLimiter:
    """Token bucket rate limiter per supplier"""

    def __init__(self, calls_per_second: float, calls_per_day: int):
        self.calls_per_second = calls_per_second
        self.calls_per_day = calls_per_day
        self.last_call = 0
        self.daily_count = 0
        self.day_reset = datetime.utcnow().date()

    def wait(self):
        """Wait if necessary to respect rate limits"""
        now = time.time()

        # Check daily limit
        if datetime.utcnow().date() > self.day_reset:
            self.daily_count = 0
            self.day_reset = datetime.utcnow().date()

        if self.daily_count >= self.calls_per_day:
            logger.warning(f"Daily rate limit reached")
            raise Exception("Daily API rate limit exceeded")

        # Check per-second limit
        min_interval = 1.0 / self.calls_per_second
        elapsed = now - self.last_call
        if elapsed < min_interval:
            time.sleep(min_interval - elapsed)

        self.last_call = time.time()
        self.daily_count += 1


class SupplierCache:
    """Simple in-memory cache with TTL"""

    def __init__(self):
        self.cache = {}

    def get(self, key: str, ttl_seconds: int = 3600) -> Optional[Any]:
        """Get cached value if still valid"""
        if key in self.cache:
            value, timestamp = self.cache[key]
            if time.time() - timestamp < ttl_seconds:
                return value
            else:
                del self.cache[key]
        return None

    def set(self, key: str, value: Any):
        """Cache a value with current timestamp"""
        self.cache[key] = (value, time.time())

    def clear(self):
        """Clear all cached values"""
        self.cache.clear()


def handle_api_errors(func):
    """Decorator to handle API errors gracefully"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except requests.RequestException as e:
            logger.error(f"API request failed in {func.__name__}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error in {func.__name__}: {e}")
            return None
    return wrapper


class BaseSupplier(ABC):
    """Base class for all supplier integrations"""

    def __init__(self, name: str):
        self.name = name
        self.cache = SupplierCache()
        self.rate_limiter = None

    @abstractmethod
    def search(self, query: str) -> List[Dict]:
        """Search for parts by query string"""
        pass

    @abstractmethod
    def get_price(self, part_number: str) -> Optional[PartPrice]:
        """Get current price for a part number"""
        pass

    @abstractmethod
    def check_stock(self, part_number: str) -> int:
        """Check quantity available for a part"""
        pass

    @abstractmethod
    def get_details(self, part_number: str) -> Optional[PartDetails]:
        """Get detailed information about a part"""
        pass

    def _generate_cache_key(self, method: str, query: str) -> str:
        """Generate cache key from method and query"""
        key_str = f"{self.name}:{method}:{query}"
        return hashlib.md5(key_str.encode()).hexdigest()


class DigiKeySupplier(BaseSupplier):
    """DigiKey API v3 Integration (OAuth2)"""

    API_BASE = "https://api.digikey.com/orders/v3"

    def __init__(self):
        super().__init__(SupplierName.DIGIKEY.value)
        self.client_id = os.getenv("DIGIKEY_CLIENT_ID", "")
        self.client_secret = os.getenv("DIGIKEY_CLIENT_SECRET", "")
        self.access_token = None
        self.token_expires = 0
        # Free tier: 1000 requests/day, ~0.01 calls/second
        self.rate_limiter = RateLimiter(calls_per_second=0.1, calls_per_day=1000)

    def _get_access_token(self) -> str:
        """Get or refresh OAuth2 access token"""
        if self.access_token and time.time() < self.token_expires:
            return self.access_token

        if not self.client_id or not self.client_secret:
            logger.warning("DigiKey credentials not configured")
            return None

        try:
            # In production, implement proper OAuth2 flow
            # For now, return placeholder
            logger.info("DigiKey OAuth2 token placeholder (configure credentials)")
            return "placeholder_token"
        except Exception as e:
            logger.error(f"Failed to get DigiKey token: {e}")
            return None

    @handle_api_errors
    def search(self, query: str) -> List[Dict]:
        """Search DigiKey catalog"""
        cache_key = self._generate_cache_key("search", query)
        cached = self.cache.get(cache_key, ttl_seconds=3600)
        if cached:
            return cached

        if self.rate_limiter:
            self.rate_limiter.wait()

        # Placeholder: DigiKey API implementation
        logger.info(f"DigiKey search: {query}")
        results = []
        return results

    @handle_api_errors
    def get_price(self, part_number: str) -> Optional[PartPrice]:
        """Get DigiKey price for part"""
        cache_key = self._generate_cache_key("price", part_number)
        cached = self.cache.get(cache_key, ttl_seconds=3600)
        if cached:
            return cached

        if self.rate_limiter:
            self.rate_limiter.wait()

        # Placeholder: DigiKey API implementation
        logger.info(f"DigiKey get_price: {part_number}")
        return None

    @handle_api_errors
    def check_stock(self, part_number: str) -> int:
        """Check DigiKey stock"""
        if self.rate_limiter:
            self.rate_limiter.wait()
        logger.info(f"DigiKey check_stock: {part_number}")
        return 0

    @handle_api_errors
    def get_details(self, part_number: str) -> Optional[PartDetails]:
        """Get DigiKey part details"""
        cache_key = self._generate_cache_key("details", part_number)
        cached = self.cache.get(cache_key, ttl_seconds=86400)
        if cached:
            return cached

        if self.rate_limiter:
            self.rate_limiter.wait()

        logger.info(f"DigiKey get_details: {part_number}")
        return None


class MouserSupplier(BaseSupplier):
    """Mouser API v2 Integration"""

    API_BASE = "https://api.mouser.com/api/v1"

    def __init__(self):
        super().__init__(SupplierName.MOUSER.value)
        self.api_key = os.getenv("MOUSER_API_KEY", "")
        # Free tier: reasonable limits
        self.rate_limiter = RateLimiter(calls_per_second=0.5, calls_per_day=1000)

    @handle_api_errors
    def search(self, query: str) -> List[Dict]:
        """Search Mouser catalog"""
        cache_key = self._generate_cache_key("search", query)
        cached = self.cache.get(cache_key, ttl_seconds=3600)
        if cached:
            return cached

        if self.rate_limiter:
            self.rate_limiter.wait()

        if not self.api_key:
            logger.warning("Mouser API key not configured")
            return []

        logger.info(f"Mouser search: {query}")
        return []

    @handle_api_errors
    def get_price(self, part_number: str) -> Optional[PartPrice]:
        """Get Mouser price"""
        cache_key = self._generate_cache_key("price", part_number)
        cached = self.cache.get(cache_key, ttl_seconds=3600)
        if cached:
            return cached

        if self.rate_limiter:
            self.rate_limiter.wait()

        logger.info(f"Mouser get_price: {part_number}")
        return None

    @handle_api_errors
    def check_stock(self, part_number: str) -> int:
        """Check Mouser stock"""
        if self.rate_limiter:
            self.rate_limiter.wait()
        logger.info(f"Mouser check_stock: {part_number}")
        return 0

    @handle_api_errors
    def get_details(self, part_number: str) -> Optional[PartDetails]:
        """Get Mouser part details"""
        cache_key = self._generate_cache_key("details", part_number)
        cached = self.cache.get(cache_key, ttl_seconds=86400)
        if cached:
            return cached

        if self.rate_limiter:
            self.rate_limiter.wait()

        logger.info(f"Mouser get_details: {part_number}")
        return None


class AutomationDirectSupplier(BaseSupplier):
    """AutomationDirect CSV Price List Scraper"""

    CATALOG_URL = "https://www.automationdirect.com"

    def __init__(self):
        super().__init__(SupplierName.AUTOMATION_DIRECT.value)
        self.catalog_file = "automation_direct_catalog.json"
        self.rate_limiter = RateLimiter(calls_per_second=0.1, calls_per_day=500)
        self._load_local_catalog()

    def _load_local_catalog(self):
        """Load cached AutomationDirect catalog from file"""
        if os.path.exists(self.catalog_file):
            try:
                with open(self.catalog_file, 'r') as f:
                    self.catalog = json.load(f)
                logger.info(f"Loaded {len(self.catalog)} parts from AutomationDirect catalog")
            except Exception as e:
                logger.error(f"Failed to load AutomationDirect catalog: {e}")
                self.catalog = {}
        else:
            self.catalog = {}

    def _save_local_catalog(self):
        """Save catalog to file"""
        try:
            with open(self.catalog_file, 'w') as f:
                json.dump(self.catalog, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save catalog: {e}")

    @handle_api_errors
    def search(self, query: str) -> List[Dict]:
        """Search local AutomationDirect catalog"""
        results = []
        query_lower = query.lower()

        for part_num, details in self.catalog.items():
            if (query_lower in part_num.lower() or
                query_lower in details.get('description', '').lower() or
                query_lower in details.get('manufacturer', '').lower()):
                results.append({
                    'part_number': part_num,
                    'description': details.get('description', ''),
                    'manufacturer': details.get('manufacturer', ''),
                    'category': details.get('category', ''),
                    'price': details.get('price', 0),
                    'stock': details.get('stock', 0)
                })

        logger.info(f"AutomationDirect search: {query} - {len(results)} results")
        return results[:100]

    @handle_api_errors
    def get_price(self, part_number: str) -> Optional[PartPrice]:
        """Get price from AutomationDirect catalog"""
        if part_number in self.catalog:
            details = self.catalog[part_number]
            return PartPrice(
                supplier=self.name,
                part_number=part_number,
                manufacturer_part_number=details.get('mfg_part_number'),
                price=float(details.get('price', 0)),
                quantity_available=int(details.get('stock', 0)),
                lead_time_days=int(details.get('lead_time', 1)),
                unit_price=float(details.get('price', 0))
            )
        return None

    @handle_api_errors
    def check_stock(self, part_number: str) -> int:
        """Check stock in local catalog"""
        if part_number in self.catalog:
            return int(self.catalog[part_number].get('stock', 0))
        return 0

    @handle_api_errors
    def get_details(self, part_number: str) -> Optional[PartDetails]:
        """Get AutomationDirect part details"""
        if part_number in self.catalog:
            details = self.catalog[part_number]
            return PartDetails(
                supplier=self.name,
                part_number=part_number,
                manufacturer_part_number=details.get('mfg_part_number'),
                manufacturer=details.get('manufacturer', ''),
                description=details.get('description', ''),
                category=details.get('category', ''),
                datasheet_url=details.get('datasheet_url'),
                specs=details.get('specs', {}),
                rohs_compliant=details.get('rohs_compliant', False),
                packaging=details.get('packaging', 'Individual')
            )
        return None

    def import_parts(self, parts: List[Dict]):
        """Import parts into local catalog"""
        for part in parts:
            self.catalog[part['part_number']] = part
        self._save_local_catalog()
        logger.info(f"Imported {len(parts)} parts into AutomationDirect catalog")


class AmazonSupplier(BaseSupplier):
    """Amazon Product Advertising API (via affiliate links)"""

    def __init__(self):
        super().__init__(SupplierName.AMAZON.value)
        self.affiliate_tag = "repairxpert-20"
        self.rate_limiter = RateLimiter(calls_per_second=0.1, calls_per_day=500)

    @handle_api_errors
    def search(self, query: str) -> List[Dict]:
        """Search Amazon for parts"""
        cache_key = self._generate_cache_key("search", query)
        cached = self.cache.get(cache_key, ttl_seconds=3600)
        if cached:
            return cached

        if self.rate_limiter:
            self.rate_limiter.wait()

        # In production, use Product Advertising API
        logger.info(f"Amazon search: {query}")
        return []

    @handle_api_errors
    def get_price(self, part_number: str) -> Optional[PartPrice]:
        """Get Amazon price"""
        cache_key = self._generate_cache_key("price", part_number)
        cached = self.cache.get(cache_key, ttl_seconds=3600)
        if cached:
            return cached

        if self.rate_limiter:
            self.rate_limiter.wait()

        logger.info(f"Amazon get_price: {part_number}")
        return None

    @handle_api_errors
    def check_stock(self, part_number: str) -> int:
        """Check Amazon stock"""
        if self.rate_limiter:
            self.rate_limiter.wait()
        logger.info(f"Amazon check_stock: {part_number}")
        return 0

    @handle_api_errors
    def get_details(self, part_number: str) -> Optional[PartDetails]:
        """Get Amazon part details"""
        cache_key = self._generate_cache_key("details", part_number)
        cached = self.cache.get(cache_key, ttl_seconds=86400)
        if cached:
            return cached

        if self.rate_limiter:
            self.rate_limiter.wait()

        logger.info(f"Amazon get_details: {part_number}")
        return None


class SupplierManager:
    """Manages all supplier instances"""

    def __init__(self):
        self.suppliers = {
            SupplierName.DIGIKEY.value: DigiKeySupplier(),
            SupplierName.MOUSER.value: MouserSupplier(),
            SupplierName.AUTOMATION_DIRECT.value: AutomationDirectSupplier(),
            SupplierName.AMAZON.value: AmazonSupplier(),
        }

    def get_supplier(self, name: str) -> Optional[BaseSupplier]:
        """Get supplier by name"""
        return self.suppliers.get(name)

    def get_all_suppliers(self) -> List[BaseSupplier]:
        """Get all suppliers"""
        return list(self.suppliers.values())

    def search_all(self, query: str) -> Dict[str, List[Dict]]:
        """Search across all suppliers"""
        results = {}
        for name, supplier in self.suppliers.items():
            try:
                results[name] = supplier.search(query)
            except Exception as e:
                logger.error(f"Search failed for {name}: {e}")
                results[name] = []
        return results

    def get_prices_all(self, part_number: str) -> Dict[str, Optional[PartPrice]]:
        """Get prices from all suppliers"""
        prices = {}
        for name, supplier in self.suppliers.items():
            try:
                prices[name] = supplier.get_price(part_number)
            except Exception as e:
                logger.error(f"Price lookup failed for {name}: {e}")
                prices[name] = None
        return prices
