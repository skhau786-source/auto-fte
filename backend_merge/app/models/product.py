from sqlalchemy import Column, Integer, String, Float, ForeignKey
from app.database import Base

class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    shopify_product_id = Column(String, unique=True, index=True)
    title = Column(String)
    vendor = Column(String)
    product_type = Column(String)
    status = Column(String)
    price = Column(Float)
    inventory = Column(Integer, default=0)

    shop_id = Column(Integer, ForeignKey("shopify_stores.id"))
    