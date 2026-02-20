"""사용자 도메인 엔티티"""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from domain.exceptions import InsufficientCreditsError


@dataclass
class UserEntity:
    """User 도메인 엔티티 — ORM 모델이 아닌 비즈니스 로직용"""
    id: int
    email: str
    name: str
    role: str  # "user" | "admin"
    plan: str  # "free" | "basic" | "enterprise"
    credits: int
    credits_used: int
    is_active: bool
    webhook_enabled: bool = False
    webhook_url: Optional[str] = None
    webhook_secret: Optional[str] = None
    api_key: Optional[str] = None
    password_hash: str = ""
    phone: Optional[str] = None
    company: Optional[str] = None
    plan_start_date: Optional[datetime] = None
    plan_end_date: Optional[datetime] = None

    @property
    def has_unlimited_credits(self) -> bool:
        return self.credits == -1

    def can_parse(self) -> bool:
        """파싱 가능 여부 (크레딧 기반)"""
        return self.has_unlimited_credits or self.credits > 0

    def deduct_credit(self, amount: int = 1) -> None:
        """크레딧 차감"""
        if not self.has_unlimited_credits:
            if self.credits < amount:
                raise InsufficientCreditsError()
            self.credits -= amount
        self.credits_used += amount
