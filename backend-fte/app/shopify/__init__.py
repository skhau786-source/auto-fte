"""
Shopify Integration Module — Digital FTE Platform.

This module provides the Shopify integration for the Digital FTE platform,
architected as its own module (mirroring ``app.woocommerce``). It handles:

- Shopify Admin API communication (GraphQL + REST) via ``shopify_client``
- Webhook reception (HMAC-verified) for real-time inventory/product updates
- Automatic webhook registration after store connection
- Background retry worker for failed Shopify synchronizations

Inventory business logic remains the responsibility of ``app.inventory``,
which consumes this module through its public API.
"""

__version__ = "1.0.0"
