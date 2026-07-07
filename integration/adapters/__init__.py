"""ERP adapter registry.

Resolve an adapter by source key so the sync service / management command can
stay format-agnostic::

    from integration.adapters import get_adapter
    adapter = get_adapter("odoo")   # or "sap"
"""

from __future__ import annotations

from .base import (
    AdapterError,
    AdapterRecordError,
    CanonicalEmployee,
    ERPAdapter,
)
from .odoo import OdooJSONAdapter
from .sap import SAPXMLAdapter

# key -> adapter class
_REGISTRY: dict[str, type[ERPAdapter]] = {
    "odoo": OdooJSONAdapter,
    "sap": SAPXMLAdapter,
}


def available_sources() -> list[str]:
    return sorted(_REGISTRY)


def get_adapter(source: str) -> ERPAdapter:
    """Return an adapter instance for ``source`` (case-insensitive)."""
    key = (source or "").strip().lower()
    try:
        return _REGISTRY[key]()
    except KeyError as exc:
        raise AdapterError(
            f"Unknown ERP source '{source}'. Available: {available_sources()}"
        ) from exc


__all__ = [
    "AdapterError",
    "AdapterRecordError",
    "CanonicalEmployee",
    "ERPAdapter",
    "OdooJSONAdapter",
    "SAPXMLAdapter",
    "available_sources",
    "get_adapter",
]
