"""Webhook 로그 ORM 모델"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.orm import relationship
from infrastructure.persistence.database import Base


class WebhookLog(Base):
    __tablename__ = "webhook_logs"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    parse_record_id = Column(Integer, ForeignKey("parse_records.id"), nullable=True)
    url = Column(String(500), nullable=False)
    event_type = Column(String(50), nullable=False)
    payload = Column(Text, nullable=True)
    status_code = Column(Integer, nullable=True)
    response_body = Column(Text, nullable=True)
    success = Column(Boolean, default=False, nullable=False)
    retry_count = Column(Integer, default=0, nullable=False)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    sent_at = Column(DateTime, nullable=True)
    user = relationship("User", back_populates="webhooks")
    parse_record = relationship("ParseRecord", back_populates="webhooks")

    def __repr__(self):
        return f"<WebhookLog {self.id} - {self.event_type}>"
