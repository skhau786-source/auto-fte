from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.sql import func
from app.database import Base


class WooCommerceStore(Base):
    __tablename__ = "woocommerce_stores"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)   # login system se bharata hai
    store_url = Column(String, unique=True, nullable=False)
    consumer_key = Column(String, nullable=False)
    consumer_secret = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())