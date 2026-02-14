"""
SQLAlchemy 데이터베이스 모델
"""
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, Text, ForeignKey, Enum, Float
)
from sqlalchemy.orm import relationship
import enum

from database import Base


class UserRole(str, enum.Enum):
    """사용자 역할"""
    USER = "user"
    ADMIN = "admin"


class PlanType(str, enum.Enum):
    """요금제 타입"""
    FREE = "free"
    BASIC = "basic"
    PRO = "pro"


class ParseStatus(str, enum.Enum):
    """파싱 상태"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class PaymentStatus(str, enum.Enum):
    """결제 상태"""
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"


class User(Base):
    """사용자 테이블"""
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    name = Column(String(100), nullable=False)
    phone = Column(String(20), nullable=True)
    company = Column(String(100), nullable=True)
    
    # 역할 및 플랜
    role = Column(Enum(UserRole), default=UserRole.USER, nullable=False)
    plan = Column(Enum(PlanType), default=PlanType.FREE, nullable=False)
    plan_start_date = Column(DateTime, nullable=True)
    plan_end_date = Column(DateTime, nullable=True)
    
    # 크레딧 (파싱 횟수)
    credits = Column(Integer, default=3, nullable=False)  # 무료: 3회
    credits_used = Column(Integer, default=0, nullable=False)
    
    # Webhook 설정
    webhook_url = Column(String(500), nullable=True)
    webhook_secret = Column(String(100), nullable=True)
    webhook_enabled = Column(Boolean, default=False)
    
    # API 키
    api_key = Column(String(64), unique=True, nullable=True)
    
    # 타임스탬프
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_login_at = Column(DateTime, nullable=True)
    
    # 상태
    is_active = Column(Boolean, default=True, nullable=False)
    is_verified = Column(Boolean, default=False, nullable=False)
    
    # 관계
    parse_records = relationship("ParseRecord", back_populates="user", cascade="all, delete-orphan")
    payments = relationship("Payment", back_populates="user", cascade="all, delete-orphan")
    webhooks = relationship("WebhookLog", back_populates="user", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<User {self.email}>"


class ParseRecord(Base):
    """파싱 기록 테이블"""
    __tablename__ = "parse_records"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # 파일 정보
    file_name = Column(String(255), nullable=False)
    file_size = Column(Integer, nullable=False)
    file_hash = Column(String(64), nullable=True)  # MD5
    
    # 파싱 결과 요약
    status = Column(Enum(ParseStatus), default=ParseStatus.PENDING, nullable=False)
    unique_number = Column(String(50), nullable=True)  # 등기부등본 고유번호
    property_type = Column(String(50), nullable=True)  # 건물/집합건물
    property_address = Column(String(500), nullable=True)
    
    # 파싱 결과 (JSON)
    result_json = Column(Text, nullable=True)  # 전체 파싱 결과
    
    # 통계
    section_a_count = Column(Integer, default=0)  # 갑구 항목 수
    section_b_count = Column(Integer, default=0)  # 을구 항목 수
    
    # 타임스탬프
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at = Column(DateTime, nullable=True)
    processing_time = Column(Float, nullable=True)  # 초 단위
    
    # 에러 정보
    error_message = Column(Text, nullable=True)
    
    # 관계
    user = relationship("User", back_populates="parse_records")
    webhooks = relationship("WebhookLog", back_populates="parse_record", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<ParseRecord {self.id} - {self.status}>"


class Payment(Base):
    """결제 내역 테이블"""
    __tablename__ = "payments"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # 결제 정보
    order_id = Column(String(100), unique=True, nullable=False)  # 주문번호
    payment_key = Column(String(100), nullable=True)  # Toss 결제 키
    
    # 플랜 정보
    plan_type = Column(Enum(PlanType), nullable=False)
    plan_name = Column(String(50), nullable=False)
    
    # 금액
    amount = Column(Integer, nullable=False)  # 결제 금액 (원)
    
    # 상태
    status = Column(Enum(PaymentStatus), default=PaymentStatus.PENDING, nullable=False)
    
    # 결제 수단
    method = Column(String(50), nullable=True)  # 카드, 가상계좌 등
    card_company = Column(String(50), nullable=True)
    card_number = Column(String(20), nullable=True)
    
    # 타임스탬프
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    paid_at = Column(DateTime, nullable=True)
    cancelled_at = Column(DateTime, nullable=True)
    
    # 추가 정보
    metadata_json = Column(Text, nullable=True)  # 기타 메타데이터
    
    # 관계
    user = relationship("User", back_populates="payments")
    
    def __repr__(self):
        return f"<Payment {self.order_id} - {self.amount}원>"


class WebhookLog(Base):
    """Webhook 발송 로그 테이블"""
    __tablename__ = "webhook_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    parse_record_id = Column(Integer, ForeignKey("parse_records.id"), nullable=True)
    
    # Webhook 정보
    url = Column(String(500), nullable=False)
    event_type = Column(String(50), nullable=False)  # parsing.completed, parsing.failed
    payload = Column(Text, nullable=True)
    
    # 응답 정보
    status_code = Column(Integer, nullable=True)
    response_body = Column(Text, nullable=True)
    
    # 상태
    success = Column(Boolean, default=False, nullable=False)
    retry_count = Column(Integer, default=0, nullable=False)
    error_message = Column(Text, nullable=True)
    
    # 타임스탬프
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    sent_at = Column(DateTime, nullable=True)
    
    # 관계
    user = relationship("User", back_populates="webhooks")
    parse_record = relationship("ParseRecord", back_populates="webhooks")
    
    def __repr__(self):
        return f"<WebhookLog {self.id} - {self.event_type}>"


class ApiKey(Base):
    """API 키 테이블"""
    __tablename__ = "api_keys"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    key = Column(String(64), unique=True, nullable=False)
    name = Column(String(100), nullable=True)  # 키 이름
    
    is_active = Column(Boolean, default=True, nullable=False)
    last_used_at = Column(DateTime, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=True)
    
    def __repr__(self):
        return f"<ApiKey {self.key[:8]}...>"
