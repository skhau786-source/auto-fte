"""
Audit Log Service — expanded audit logging for all inventory operations.

Every operation captures:
- User (ID, email)
- Store (ID, domain)
- IP address
- Endpoint
- Timestamp
- Action type
- Before values (state snapshot)
- After values (state snapshot)
- Reason / Change note
- Correlation ID (trace operations across services)
- Request ID (from request context)
- Duration (execution time)

Supports export to CSV and JSON formats.
"""

import uuid
import csv
import json
import io
import logging
from typing import Optional, Any
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import InventoryLog, ProductVariant, Product
from app.inventory.repository import LogRepository

logger = logging.getLogger(__name__)


class AuditContext:
    """Context for a single audit operation, capturing request-scoped data."""

    def __init__(
        self,
        user_id: Optional[uuid.UUID] = None,
        user_email: Optional[str] = None,
        store_id: Optional[uuid.UUID] = None,
        store_domain: Optional[str] = None,
        ip_address: Optional[str] = None,
        endpoint: Optional[str] = None,
        request_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ):
        self.user_id = user_id
        self.user_email = user_email
        self.store_id = store_id
        self.store_domain = store_domain
        self.ip_address = ip_address
        self.endpoint = endpoint
        self.request_id = request_id
        self.correlation_id = correlation_id or str(uuid.uuid4())
        self.timestamp = datetime.now(timezone.utc)


class AuditService:
    """Enhanced audit logging with context, before/after snapshots, and export support."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.log_repo = LogRepository(db)

    async def log_operation(
        self,
        variant_id: uuid.UUID,
        action: str,
        context: AuditContext,
        before_values: Optional[dict[str, Any]] = None,
        after_values: Optional[dict[str, Any]] = None,
        reason: Optional[str] = None,
        duration_ms: Optional[float] = None,
    ) -> InventoryLog:
        """
        Log an inventory operation with full audit context.

        Args:
            variant_id: The variant that was modified.
            action: The action performed (e.g., 'inventory_adjusted', 'created').
            context: Audit context with user, store, IP, request info.
            before_values: Snapshot of state before the change.
            after_values: Snapshot of state after the change.
            reason: Human-readable reason for the change.
            duration_ms: How long the operation took.

        Returns:
            The created InventoryLog record.
        """
        details = {}

        if context.store_id:
            details["store_id"] = str(context.store_id)
        if context.store_domain:
            details["store_domain"] = context.store_domain
        if context.user_email:
            details["user_email"] = context.user_email
        if context.ip_address:
            details["ip_address"] = context.ip_address
        if context.endpoint:
            details["endpoint"] = context.endpoint
        if context.request_id:
            details["request_id"] = context.request_id
        if context.correlation_id:
            details["correlation_id"] = context.correlation_id
        if before_values:
            details["before"] = before_values
        if after_values:
            details["after"] = after_values
        if reason:
            details["reason"] = reason
        if duration_ms is not None:
            details["duration_ms"] = duration_ms

        return await self.log_repo.create(
            variant_id=variant_id,
            action=action,
            details=details,
            performed_by=context.user_id,
        )

    # ═══════════════════════════════════════════════════════════════
    # Export Methods
    # ═══════════════════════════════════════════════════════════════

    async def export_logs(
        self,
        store_id: uuid.UUID,
        format: str = "json",
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        action: Optional[str] = None,
        limit: int = 1000,
    ) -> tuple[str, str]:
        """
        Export audit logs for a store.

        Args:
            store_id: The store whose logs to export.
            format: 'json' or 'csv'.
            date_from: Optional start date filter.
            date_to: Optional end date filter.
            action: Optional action type filter.
            limit: Maximum number of logs to export.

        Returns:
            Tuple of (content_type, export_data_string).
        """
        from sqlalchemy import select as sel

        query = (
            sel(InventoryLog)
            .join(ProductVariant, InventoryLog.variant_id == ProductVariant.id)
            .join(Product, ProductVariant.product_id == Product.id)
            .where(Product.store_id == store_id)
        )

        if date_from:
            query = query.where(InventoryLog.created_at >= date_from)
        if date_to:
            query = query.where(InventoryLog.created_at <= date_to)
        if action:
            query = query.where(InventoryLog.action == action)

        query = query.order_by(InventoryLog.created_at.desc()).limit(limit)

        result = await self.db.execute(query)
        logs = list(result.scalars().all())

        if format == "csv":
            return self._to_csv(logs)
        else:
            return self._to_json(logs)

    def _to_json(self, logs: list[InventoryLog]) -> tuple[str, str]:
        """Convert logs to JSON format."""
        data = []
        for log in logs:
            entry = {
                "id": str(log.id),
                "variant_id": str(log.variant_id),
                "action": log.action,
                "details": log.details,
                "performed_by": str(log.performed_by) if log.performed_by else None,
                "created_at": log.created_at.isoformat(),
            }
            data.append(entry)

        return "application/json", json.dumps(data, indent=2, default=str)

    def _to_csv(self, logs: list[InventoryLog]) -> tuple[str, str]:
        """Convert logs to CSV format."""
        output = io.StringIO()
        writer = csv.writer(output)

        writer.writerow([
            "id",
            "variant_id",
            "action",
            "details",
            "performed_by",
            "created_at",
        ])

        for log in logs:
            writer.writerow([
                str(log.id),
                str(log.variant_id),
                log.action,
                json.dumps(log.details, default=str),
                str(log.performed_by) if log.performed_by else "",
                log.created_at.isoformat(),
            ])

        return "text/csv", output.getvalue()

    async def export_transactions(
        self,
        store_id: uuid.UUID,
        format: str = "json",
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        limit: int = 1000,
    ) -> tuple[str, str]:
        """Export inventory transactions for a store."""
        from app.inventory.repository import TransactionRepository
        txn_repo = TransactionRepository(self.db)

        transactions, _ = await txn_repo.list_history(
            store_id=store_id,
            date_from=date_from,
            date_to=date_to,
            page=1,
            page_size=limit,
        )

        if format == "csv":
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow([
                "id", "variant_id", "transaction_type", "quantity_change",
                "quantity_before", "quantity_after", "reason", "performed_by",
                "synced_to_shopify", "created_at",
            ])
            for txn in transactions:
                writer.writerow([
                    str(txn.id), str(txn.variant_id), txn.transaction_type,
                    txn.quantity_change, txn.quantity_before, txn.quantity_after,
                    txn.reason or "", str(txn.performed_by or ""),
                    txn.synced_to_shopify, txn.created_at.isoformat(),
                ])
            return "text/csv", output.getvalue()
        else:
            data = [
                {
                    "id": str(t.id),
                    "variant_id": str(t.variant_id),
                    "transaction_type": t.transaction_type,
                    "quantity_change": t.quantity_change,
                    "quantity_before": t.quantity_before,
                    "quantity_after": t.quantity_after,
                    "reason": t.reason,
                    "performed_by": str(t.performed_by) if t.performed_by else None,
                    "synced_to_shopify": t.synced_to_shopify,
                    "created_at": t.created_at.isoformat(),
                }
                for t in transactions
            ]
            return "application/json", json.dumps(data, indent=2, default=str)
