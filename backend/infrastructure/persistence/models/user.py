"""사용자 ORM 모델"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Enum
from sqlalchemy.orm import relationship
from infrastructure.persistence.database import Base
from domain.enums import UserRole, PlanType


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    name = Column(String(100), nullable=False)
    phone = Column(String(20), nullable=True)
    company = Column(String(100), nullable=True)
    role = Column(Enum(UserRole), default=UserRole.USER, nullable=False)
    plan = Column(Enum(PlanType), default=PlanType.FREE, nullable=False)
    plan_start_date = Column(DateTime, nullable=True)
    plan_end_date = Column(DateTime, nullable=True)
    credits = Column(Integer, default=3, nullable=False)
    credits_used = Column(Integer, default=0, nullable=False)
    webhook_url = Column(String(500), nullable=True)
    webhook_secret = Column(String(100), nullable=True)
    webhook_enabled = Column(Boolean, default=False)
    api_key = Column(String(64), unique=True, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_login_at = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    is_verified = Column(Boolean, default=False, nullable=False)
    parse_records = relationship("ParseRecord", back_populates="user", cascade="all, delete-orphan")
    payments = relationship("Payment", back_populates="user", cascade="all, delete-orphan")
    webhooks = relationship("WebhookLog", back_populates="user", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<User {self.email}>"
