"""사용자 설정 + Webhook 스키마"""
from datetime import datetime
from typing import Optional, Dict, Any
from pydantic import BaseModel


class UserSettingsUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    company: Optional[str] = None
    webhook_enabled: Optional[bool] = None
    webhook_url: Optional[str] = None
    webhook_secret: Optional[str] = None


class ApiKeyResponse(BaseModel):
    key: str
    name: Optional[str]
    created_at: datetime
    last_used_at: Optional[datetime]
    is_active: bool


class WebhookSettingRequest(BaseModel):
    enabled: bool
    url: Optional[str] = None
    secret: Optional[str] = None


class WebhookPayload(BaseModel):
    event: str
    timestamp: str
    data: Dict[str, Any]
    signature: str


class WebhookLogItem(BaseModel):
    id: int
    url: str
    event_type: str
    success: bool
    status_code: Optional[int]
    retry_count: int
    created_at: datetime

    class Config:
        from_attributes = True
