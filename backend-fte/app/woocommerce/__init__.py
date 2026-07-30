"""
WooCommerce Inventory Sync Agent — Digital FTE Platform.

This module provides a complete WooCommerce integration for the Digital FTE
multi-agent AI platform. It handles:

- WooCommerce store authentication (Consumer Key / Consumer Secret)
- Product, Inventory, Order, Customer, Category, and Coupon synchronization
- Webhook reception for real-time updates
- Background sync jobs via Celery
- Low stock alerts and notifications
- Audit logging for all operations

All AI agents (Content, Customer Support, Analytics, Recommendation, Marketing)
consume normalized inventory data through the public API layer.
"""

__version__ = "1.0.0"
