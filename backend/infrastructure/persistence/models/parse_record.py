"""파싱 기록 ORM 모델"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, Enum, Float
from sqlalchemy.orm import relationship
from infrastructure.persistence.database import Base
from domain.enums import ParseStatus


class ParseRecord(Base):
    __tablename__ = "parse_records"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    file_name = Column(String(255), nullable=False)
    file_size = Column(Integer, nullable=False)
    file_hash = Column(String(64), nullable=True)
    status = Column(Enum(ParseStatus), default=ParseStatus.PENDING, nullable=False)
    unique_number = Column(String(50), nullable=True)
    property_type = Column(String(50), nullable=True)
    property_address = Column(String(500), nullable=True)
    document_type = Column(String(50), default="registry", nullable=True)
    parser_version = Column(String(20), nullable=True)
    result_json = Column(Text, nullable=True)
    section_a_count = Column(Integer, default=0)
    section_b_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at = Column(DateTime, nullable=True)
    processing_time = Column(Float, nullable=True)
    error_message = Column(Text, nullable=True)
    user = relationship("User", back_populates="parse_records")
    webhooks = relationship("WebhookLog", back_populates="parse_record", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<ParseRecord {self.id} - {self.status}>"
