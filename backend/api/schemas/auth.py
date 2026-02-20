"""인증 관련 스키마"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, Field, field_validator


class UserSignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=100)
    name: str = Field(..., min_length=2, max_length=100)
    phone: Optional[str] = Field(None, max_length=20)
    company: Optional[str] = Field(None, max_length=100)

    @field_validator('password')
    @classmethod
    def validate_password(cls, v):
        if not any(c.isupper() for c in v):
            raise ValueError('비밀번호에는 최소 1개의 대문자가 포함되어야 합니다.')
        if not any(c.islower() for c in v):
            raise ValueError('비밀번호에는 최소 1개의 소문자가 포함되어야 합니다.')
        if not any(c.isdigit() for c in v):
            raise ValueError('비밀번호에는 최소 1개의 숫자가 포함되어야 합니다.')
        return v


class UserLoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class UserResponse(BaseModel):
    id: int
    email: str
    name: str
    phone: Optional[str]
    company: Optional[str]
    role: str
    plan: str
    plan_end_date: Optional[datetime]
    credits: int
    credits_used: int
    webhook_enabled: bool
    webhook_url: Optional[str]
    api_key: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True
