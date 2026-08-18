from sqlalchemy import Column, Integer, String, Float, ForeignKey
from app.database import Base


class WooCommerceProduct(Base):
    __tablename__ = "woocommerce_products"

    id = Column(Integer, primary_key=True, index=True)
    woocommerce_product_id = Column(String, index=True)  # WooCommerce ki apni product ID
    title = Column(String)
    sku = Column(String, nullable=True)
    price = Column(Float, nullable=True)
    inventory = Column(Integer, default=0)
    stock_status = Column(String, nullable=True)  # "instock" / "outofstock"
    image_url = Column(String, nullable=True)
    store_id = Column(Integer, ForeignKey("woocommerce_stores.id"))
