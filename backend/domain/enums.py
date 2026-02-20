"""도메인 열거형"""
import enum


class UserRole(str, enum.Enum):
    USER = "user"
    ADMIN = "admin"


class PlanType(str, enum.Enum):
    FREE = "free"
    BASIC = "basic"
    ENTERPRISE = "enterprise"


class ParseStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class PaymentStatus(str, enum.Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"
