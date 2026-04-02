"""Parts search — search across supplier sites for pricing and availability.

Provides a unified search function that builds search URLs for each supplier.
Actual price lookups would require API keys / web scraping in production.
For now, returns catalog data with pre-built search URLs.
"""
from indauto.parts.catalog import get_parts_for_category, AMAZON_TAG


# Supplier search URL builders
SUPPLIER_SEARCH_URLS = {
    "AutomationDirect": "https://www.automationdirect.com/adc/shopping/catalog?searchText={query}",
    "Amazon": f"https://www.amazon.com/s?k={{query}}&tag={AMAZON_TAG}",
    "McMaster-Carr": "https://www.mcmaster.com/{query}",
    "Grainger": "https://www.grainger.com/search?searchQuery={query}",
    "Digikey": "https://www.digikey.com/en/products/result?keywords={query}",
    "Mouser": "https://www.mouser.com/Search/Refine?Keyword={query}",
    "Omega": "https://www.omega.com/en-us/search/?q={query}",
}


def build_search_url(supplier: str, query: str) -> str:
    """Build a supplier search URL for a given query string."""
    import urllib.parse
    encoded = urllib.parse.quote_plus(query)
    template = SUPPLIER_SEARCH_URLS.get(supplier)
    if template:
        return template.format(query=encoded)
    # Fallback: Google Shopping search
    return f"https://www.google.com/search?tbm=shop&q={encoded}"


def search_parts(query: str, category: str = "") -> dict:
    """Search for parts matching a query, optionally filtered by category.

    Args:
        query: Free-text search (e.g., "18mm proximity sensor")
        category: Optional parts_category to filter by

    Returns:
        Dict with:
            - parts: list of matching parts from catalog
            - search_links: dict of supplier name -> search URL for the query
    """
    parts = []

    # If category provided, get catalog parts
    if category:
        parts = get_parts_for_category(category)

    # If no category or no matches, try keyword matching across all categories
    if not parts and query:
        from indauto.parts.catalog import PARTS_CATALOG
        q_lower = query.lower()
        for cat_parts in PARTS_CATALOG.values():
            for part in cat_parts:
                searchable = f"{part['name']} {part.get('part_no', '')} {part.get('description', '')}".lower()
                if q_lower in searchable or any(w in searchable for w in q_lower.split() if len(w) > 3):
                    if part not in parts:
                        parts.append(part)

    # Build search URLs for direct supplier searches
    search_query = query or category.replace("_", " ")
    search_links = {
        name: build_search_url(name, search_query)
        for name in ["AutomationDirect", "Amazon", "McMaster-Carr", "Grainger", "Digikey"]
    }

    return {
        "parts": parts,
        "search_links": search_links,
        "query": search_query,
    }
