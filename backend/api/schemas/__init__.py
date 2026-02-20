"""
API 스키마 — 기존 schemas.py의 모든 클래스를 re-export

사용법:
  from api.schemas import ParseResponse, UserResponse  # 새 경로
  from schemas import ParseResponse, UserResponse       # 기존 경로 (심으로 유지)
"""
from api.schemas.common import ResponseBase
from api.schemas.auth import (
    UserSignupRequest, UserLoginRequest, TokenResponse, UserResponse,
)
from api.schemas.parse import (
    FloorArea, OwnerInfo, CreditorInfo, LesseeInfo, LeaseTermInfo,
    CancellationInfo, SectionAEntry, SectionBEntry,
    LandTitleEntry, BuildingTitleEntry, ExclusivePartEntry,
    LandRightEntry, LandRightRatioEntry, TitleInfo, RegistryData,
    ParseRequest, ParseResponse, ParseHistoryItem, ParseHistoryResponse,
)
from api.schemas.payment import (
    PlanInfo, PricingResponse, PaymentRequest, PaymentResponse,
    PaymentConfirmRequest, PaymentHistoryItem, PaymentHistoryResponse,
)
from api.schemas.user import (
    UserSettingsUpdate, ApiKeyResponse,
    WebhookSettingRequest, WebhookPayload, WebhookLogItem,
)
