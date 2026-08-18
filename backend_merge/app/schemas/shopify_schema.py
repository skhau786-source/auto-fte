from pydantic import BaseModel
from typing import Optional

class ShopifyConnectRequest(BaseModel):
    shop: str

class ShopifyStoreResponse(BaseModel):
    id: int
    shop_url: str
    scope: Optional[str] = None

    class Config:
        from_attributes = True
