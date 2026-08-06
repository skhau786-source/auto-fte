"""
Dependency injection for the Inventory Management module.

Reuses the existing auth dependency (get_current_user) and database session
(get_db) to resolve the authenticated user's active Shopify store.
"""

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models import RegisteredStudent, Store


async def get_store_for_user(
    user: RegisteredStudent = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Store:
    """
    Resolve the active Shopify store for the authenticated user.

    This is the bridge between Team Member 2's Store Connection module
    and the Inventory module. Every inventory operation is scoped to
    the store returned by this dependency.

    Raises 404 if the user has no active Shopify store connected.
    """
    result = await db.execute(
        select(Store).where(
            Store.owner_id == user.id,
            Store.is_active == True,  # noqa: E712
        )
    )
    store = result.scalar_one_or_none()

    if store is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "message": "No active Shopify store found for this user",
                "error_code": "STORE_NOT_FOUND",
            },
        )

    return store
