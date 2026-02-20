"""결제 관련 스키마"""
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel
from api.schemas.common import ResponseBase


class PlanInfo(BaseModel):
    type: str
    name: str
    price: int
    credits: int
    features: List[str]


class PricingResponse(BaseModel):
    plans: List[PlanInfo]


class PaymentRequest(BaseModel):
    plan_type: str
    success_url: str
    fail_url: str


class PaymentResponse(ResponseBase):
    order_id: str
    order_name: str
    amount: int
    plan_type: str
    customer_name: str
    customer_email: str


class PaymentConfirmRequest(BaseModel):
    payment_key: str
    order_id: str
    amount: int


class PaymentHistoryItem(BaseModel):
    id: int
    order_id: str
    plan_type: str
    plan_name: str
    amount: int
    status: str
    method: Optional[str]
    created_at: datetime
    paid_at: Optional[datetime]

    class Config:
        from_attributes = True


class PaymentHistoryResponse(ResponseBase):
    items: List[PaymentHistoryItem]
    total: int
