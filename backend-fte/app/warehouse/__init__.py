"""
Warehouse & Multi-location Inventory Management Module — Digital FTE Platform.

Extends the existing Inventory Core with production-grade Warehouse Management:
- Warehouse CRUD with capacity tracking
- Multi-location inventory (per-warehouse stock levels)
- Warehouse transfers with approval workflow
- Inventory aggregation across locations
- Stock reservations and release
- Capacity monitoring and alerts

All inventory flows through this module after passing through the Inventory Core.
Platform-agnostic — works with Shopify, WooCommerce, and future connectors.
"""

__version__ = "1.0.0"
