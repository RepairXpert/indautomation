"""Parts ordering module — maps fault categories to replacement parts with supplier links."""
from indauto.parts.catalog import get_parts_for_category, PARTS_CATALOG
from indauto.parts.search import search_parts

__all__ = ["get_parts_for_category", "search_parts", "PARTS_CATALOG"]
