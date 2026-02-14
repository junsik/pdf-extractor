"""
Pydantic 스키마 - 요청/응답 데이터 검증
"""
from datetime import datetime
from typing import Optional, List, Any, Dict
from pydantic import BaseModel, EmailStr, Field, field_validator
import enum


# ==================== 공통 스키마 ====================

class ResponseBase(BaseModel):
    """기본 응답 스키마"""
    success: bool = True
    message: Optional[str] = None


# ==================== 인증 관련 스키마 ====================

class UserSignupRequest(BaseModel):
    """회원가입 요청"""
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
    """로그인 요청"""
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    """토큰 응답"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # 초 단위


class UserResponse(BaseModel):
    """사용자 정보 응답"""
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


# ==================== PDF 파싱 관련 스키마 ====================

class FloorArea(BaseModel):
    """층별 면적"""
    floor: str
    area: float
    is_excluded: bool = False


class OwnerInfo(BaseModel):
    """소유자 정보"""
    name: str
    resident_number: Optional[str] = None
    address: Optional[str] = None
    share: Optional[str] = None


class CreditorInfo(BaseModel):
    """채권자 정보"""
    name: str
    resident_number: Optional[str] = None
    address: Optional[str] = None


class LesseeInfo(BaseModel):
    """임차권자 정보"""
    name: str
    resident_number: Optional[str] = None
    address: Optional[str] = None


class LeaseTermInfo(BaseModel):
    """임대차 기간 정보"""
    contract_date: Optional[str] = None
    resident_registration_date: Optional[str] = None
    possession_start_date: Optional[str] = None
    fixed_date: Optional[str] = None


class CancellationInfo(BaseModel):
    """말소 정보"""
    is_cancelled: bool = False
    cancellation_rank_number: Optional[str] = None  # 말소 등기의 순위번호
    cancellation_date: Optional[str] = None
    cancellation_cause: Optional[str] = None
    cancels_rank_number: Optional[str] = None  # 이 등기가 말소하는 원본 순위번호


class SectionAEntry(BaseModel):
    """갑구 항목 (소유권에 관한 사항)"""
    rank_number: str
    registration_type: str
    receipt_date: str
    receipt_number: str
    registration_cause: Optional[str] = None
    registration_cause_date: Optional[str] = None
    owner: Optional[OwnerInfo] = None
    creditor: Optional[CreditorInfo] = None
    claim_amount: Optional[int] = None
    
    # 말소 관련
    is_cancelled: bool = False
    cancellation_rank_number: Optional[str] = None
    cancellation_date: Optional[str] = None
    cancellation_cause: Optional[str] = None
    cancels_rank_number: Optional[str] = None
    
    # 원본 텍스트
    raw_text: Optional[str] = None


class SectionBEntry(BaseModel):
    """을구 항목 (소유권 이외의 권리)"""
    rank_number: str
    registration_type: str
    receipt_date: str
    receipt_number: str
    registration_cause: Optional[str] = None
    registration_cause_date: Optional[str] = None
    
    # 근저당권 관련
    max_claim_amount: Optional[int] = None
    debtor: Optional[OwnerInfo] = None
    mortgagee: Optional[CreditorInfo] = None
    
    # 임차권 관련
    deposit_amount: Optional[int] = None
    monthly_rent: Optional[int] = None
    lease_term: Optional[LeaseTermInfo] = None
    lessee: Optional[LesseeInfo] = None
    lease_area: Optional[str] = None
    
    # 말소 관련
    is_cancelled: bool = False
    cancellation_rank_number: Optional[str] = None
    cancellation_date: Optional[str] = None
    cancellation_cause: Optional[str] = None
    cancels_rank_number: Optional[str] = None
    
    # 원본 텍스트
    raw_text: Optional[str] = None


class TitleInfo(BaseModel):
    """표제부 정보"""
    unique_number: str
    property_type: str  # building, aggregate_building
    address: str
    road_address: Optional[str] = None
    building_name: Optional[str] = None
    structure: Optional[str] = None
    roof_type: Optional[str] = None
    floors: Optional[int] = None
    building_type: Optional[str] = None
    areas: List[FloorArea] = []
    land_right_ratio: Optional[str] = None
    exclusive_area: Optional[float] = None
    total_floor_area: Optional[float] = None


class RegistryData(BaseModel):
    """등기부등본 전체 데이터"""
    unique_number: str
    property_type: str
    property_address: str
    title_info: TitleInfo
    section_a: List[SectionAEntry] = []
    section_b: List[SectionBEntry] = []
    raw_text: Optional[str] = None
    parse_date: str
    
    # 통계
    section_a_count: int = 0
    section_b_count: int = 0
    active_section_a_count: int = 0  # 말소되지 않은 갑구 항목
    active_section_b_count: int = 0  # 말소되지 않은 을구 항목


class ParseRequest(BaseModel):
    """파싱 요청"""
    webhook_url: Optional[str] = None
    demo_mode: bool = False


class ParseResponse(ResponseBase):
    """파싱 응답"""
    request_id: str
    status: str
    data: Optional[RegistryData] = None
    error: Optional[str] = None
    is_demo: bool = False
    remaining_credits: int = 0


class ParseHistoryItem(BaseModel):
    """파싱 기록 항목"""
    id: int
    file_name: str
    status: str
    unique_number: Optional[str]
    property_address: Optional[str]
    section_a_count: int
    section_b_count: int
    created_at: datetime
    completed_at: Optional[datetime]
    processing_time: Optional[float]
    
    class Config:
        from_attributes = True


class ParseHistoryResponse(ResponseBase):
    """파싱 기록 응답"""
    items: List[ParseHistoryItem]
    total: int
    page: int
    page_size: int


# ==================== 결제 관련 스키마 ====================

class PlanInfo(BaseModel):
    """요금제 정보"""
    type: str
    name: str
    price: int
    credits: int
    features: List[str]


class PricingResponse(BaseModel):
    """요금제 목록 응답"""
    plans: List[PlanInfo]


class PaymentRequest(BaseModel):
    """결제 요청"""
    plan_type: str  # free, basic, pro
    success_url: str
    fail_url: str


class PaymentResponse(ResponseBase):
    """결제 응답 (프론트엔드 Toss SDK에 전달할 주문 정보)"""
    order_id: str
    order_name: str
    amount: int
    plan_type: str
    customer_name: str
    customer_email: str


class PaymentConfirmRequest(BaseModel):
    """결제 확인 요청 (Toss 웹훅)"""
    payment_key: str
    order_id: str
    amount: int


class PaymentHistoryItem(BaseModel):
    """결제 내역 항목"""
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
    """결제 내역 응답"""
    items: List[PaymentHistoryItem]
    total: int


# ==================== Webhook 관련 스키마 ====================

class WebhookSettingRequest(BaseModel):
    """Webhook 설정 요청"""
    enabled: bool
    url: Optional[str] = None
    secret: Optional[str] = None


class WebhookPayload(BaseModel):
    """Webhook 페이로드"""
    event: str  # parsing.completed, parsing.failed
    timestamp: str
    data: Dict[str, Any]
    signature: str


class WebhookLogItem(BaseModel):
    """Webhook 로그 항목"""
    id: int
    url: str
    event_type: str
    success: bool
    status_code: Optional[int]
    retry_count: int
    created_at: datetime
    
    class Config:
        from_attributes = True


# ==================== 사용자 설정 스키마 ====================

class UserSettingsUpdate(BaseModel):
    """사용자 설정 업데이트"""
    name: Optional[str] = None
    phone: Optional[str] = None
    company: Optional[str] = None
    webhook_enabled: Optional[bool] = None
    webhook_url: Optional[str] = None
    webhook_secret: Optional[str] = None


class ApiKeyResponse(BaseModel):
    """API 키 응답"""
    key: str
    name: Optional[str]
    created_at: datetime
    last_used_at: Optional[datetime]
    is_active: bool
