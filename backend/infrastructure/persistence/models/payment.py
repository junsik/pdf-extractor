"""결제 ORM 모델"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, Enum
from sqlalchemy.orm import relationship
from infrastructure.persistence.database import Base
from domain.enums import PlanType, PaymentStatus


class Payment(Base):
    __tablename__ = "payments"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    order_id = Column(String(100), unique=True, nullable=False)
    payment_key = Column(String(100), nullable=True)
    plan_type = Column(Enum(PlanType), nullable=False)
    plan_name = Column(String(50), nullable=False)
    amount = Column(Integer, nullable=False)
    status = Column(Enum(PaymentStatus), default=PaymentStatus.PENDING, nullable=False)
    method = Column(String(50), nullable=True)
    card_company = Column(String(50), nullable=True)
    card_number = Column(String(20), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    paid_at = Column(DateTime, nullable=True)
    cancelled_at = Column(DateTime, nullable=True)
    metadata_json = Column(Text, nullable=True)
    user = relationship("User", back_populates="payments")

    def __repr__(self):
        return f"<Payment {self.order_id} - {self.amount}원>"
