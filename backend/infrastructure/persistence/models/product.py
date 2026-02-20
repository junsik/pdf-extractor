"""상품(문서 파서) ORM 모델"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text
from infrastructure.persistence.database import Base


class Product(Base):
    __tablename__ = "products"
    id = Column(String(50), primary_key=True)
    name = Column(String(100), nullable=False)
    parser_key = Column(String(50), nullable=False)
    credit_cost = Column(Integer, default=1)
    is_enabled = Column(Boolean, default=True)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<Product {self.id} - {self.name}>"
