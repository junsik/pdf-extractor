"""
등기부등본 PDF 파싱 서비스 - FastAPI 메인 애플리케이션
"""
import os
import io
import uuid
import asyncio
from datetime import datetime, date
from typing import Optional
from contextlib import asynccontextmanager

from fastapi import (
    FastAPI, UploadFile, File, Form, Depends, HTTPException, 
    status, BackgroundTasks, Query
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from config import settings
from database import init_db, get_session
from models import (
    User, ParseRecord, Payment, WebhookLog,
    UserRole, PlanType, ParseStatus, PaymentStatus
)
from schemas import (
    UserSignupRequest, UserLoginRequest, TokenResponse, UserResponse,
    ParseResponse, ParseHistoryResponse, ParseHistoryItem,
    PricingResponse, PlanInfo, PaymentRequest, PaymentResponse,
    PaymentConfirmRequest, PaymentHistoryResponse, PaymentHistoryItem,
    WebhookSettingRequest, WebhookPayload, UserSettingsUpdate,
    ResponseBase
)
from auth import (
    hash_password, verify_password, create_access_token, create_refresh_token,
    get_current_user, get_current_active_user, generate_api_key
)
from pdf_parser import parse_registry_pdf, mask_for_demo
from payment import PaymentService
from webhook import send_webhook, webhook_sender

from loguru import logger

# 로깅 설정
os.makedirs("./logs", exist_ok=True)
logger.add(
    settings.LOG_FILE,
    rotation="10 MB",
    retention="30 days",
    level=settings.LOG_LEVEL
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """애플리케이션 수명 주기 관리"""
    # 시작 시
    logger.info("서비스 시작...")
    await init_db()
    logger.info("데이터베이스 초기화 완료")
    
    yield
    
    # 종료 시
    logger.info("서비스 종료...")


# FastAPI 앱 생성
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="등기부등본 PDF 파싱 서비스 - 표제부, 갑구, 을구 자동 분석",
    lifespan=lifespan
)

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==================== 인증 API ====================

@app.post("/api/auth/signup", response_model=ResponseBase, tags=["인증"])
async def signup(
    request: UserSignupRequest,
    session: AsyncSession = Depends(get_session)
):
    """회원가입"""
    # 이메일 중복 확인
    result = await session.execute(
        select(User).where(User.email == request.email)
    )
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="이미 등록된 이메일입니다."
        )
    
    # 사용자 생성
    user = User(
        email=request.email,
        password_hash=hash_password(request.password),
        name=request.name,
        phone=request.phone,
        company=request.company,
        role=UserRole.USER,
        plan=PlanType.FREE,
        credits=settings.PRICING["free"]["credits"],
        api_key=generate_api_key()
    )
    
    session.add(user)
    await session.flush()
    
    logger.info(f"새 사용자 가입: {user.email}")
    
    return ResponseBase(
        success=True,
        message="회원가입이 완료되었습니다."
    )


@app.post("/api/auth/login", response_model=TokenResponse, tags=["인증"])
async def login(
    request: UserLoginRequest,
    session: AsyncSession = Depends(get_session)
):
    """로그인"""
    # 사용자 조회
    result = await session.execute(
        select(User).where(User.email == request.email)
    )
    user = result.scalar_one_or_none()
    
    if not user or not verify_password(request.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="이메일 또는 비밀번호가 올바르지 않습니다."
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="비활성화된 계정입니다."
        )
    
    # 마지막 로그인 시간 업데이트
    user.last_login_at = datetime.utcnow()
    
    # 토큰 생성
    access_token = create_access_token({"sub": user.id})
    refresh_token = create_refresh_token({"sub": user.id})
    
    logger.info(f"사용자 로그인: {user.email}")
    
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )


@app.get("/api/auth/me", response_model=UserResponse, tags=["인증"])
async def get_me(
    current_user: User = Depends(get_current_active_user)
):
    """현재 사용자 정보 조회"""
    return UserResponse(
        id=current_user.id,
        email=current_user.email,
        name=current_user.name,
        phone=current_user.phone,
        company=current_user.company,
        role=current_user.role.value,
        plan=current_user.plan.value,
        plan_end_date=current_user.plan_end_date,
        credits=current_user.credits,
        credits_used=current_user.credits_used,
        webhook_enabled=current_user.webhook_enabled,
        webhook_url=current_user.webhook_url,
        api_key=current_user.api_key,
        created_at=current_user.created_at
    )


# ==================== PDF 파싱 API ====================

@app.post("/api/parse", response_model=ParseResponse, tags=["PDF 파싱"])
async def parse_pdf(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    demo_mode: bool = Form(False),
    webhook_url: Optional[str] = Form(None),
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_session)
):
    """
    PDF 파싱
    
    - **file**: PDF 파일
    - **demo_mode**: 데모 모드 (개인정보 마스킹)
    - **webhook_url**: 파싱 완료 시 알림받을 URL
    """
    request_id = str(uuid.uuid4())

    # 파일 검증
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="PDF 파일만 업로드 가능합니다."
        )

    # 파일 크기 확인
    content = await file.read()
    if len(content) > settings.MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"파일 크기는 {settings.MAX_FILE_SIZE // 1024 // 1024}MB 이하여야 합니다."
        )

    # 크레딧 확인 (무제한이 아닌 경우)
    remaining_credits = current_user.credits
    if current_user.credits != -1 and current_user.credits <= 0:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="크레딧이 부족합니다. 요금제를 업그레이드 해주세요."
        )

    # 일일 파싱 한도 확인
    plan_key = current_user.plan.value if current_user.plan else "free"
    daily_limit = settings.PRICING.get(plan_key, {}).get("daily_limit", 3)
    if daily_limit != -1:
        today_start = datetime.combine(date.today(), datetime.min.time())
        today_count_result = await session.execute(
            select(func.count(ParseRecord.id)).where(
                ParseRecord.user_id == current_user.id,
                ParseRecord.created_at >= today_start
            )
        )
        today_count = today_count_result.scalar() or 0
        if today_count >= daily_limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"일일 파싱 한도({daily_limit}회)를 초과했습니다. 내일 다시 시도하거나 요금제를 업그레이드 해주세요."
            )

    # 파싱 기록 생성
    parse_record = ParseRecord(
        user_id=current_user.id,
        file_name=file.filename,
        file_size=len(content),
        status=ParseStatus.PROCESSING
    )
    session.add(parse_record)
    await session.flush()
    
    try:
        # PDF 파싱 실행
        start_time = datetime.utcnow()
        parsed_data = parse_registry_pdf(content)
        processing_time = (datetime.utcnow() - start_time).total_seconds()
        
        # 데모 모드면 마스킹
        if demo_mode:
            response_data = mask_for_demo(parsed_data)
        else:
            response_data = parsed_data
        
        # 파싱 기록 업데이트
        parse_record.status = ParseStatus.COMPLETED
        parse_record.unique_number = parsed_data.get("unique_number", "")
        parse_record.property_type = parsed_data.get("property_type", "")
        parse_record.property_address = parsed_data.get("property_address", "")
        parse_record.result_json = str(parsed_data)  # JSON 문자열로 저장
        parse_record.section_a_count = len(parsed_data.get("section_a", []))
        parse_record.section_b_count = len(parsed_data.get("section_b", []))
        parse_record.completed_at = datetime.utcnow()
        parse_record.processing_time = processing_time
        
        # 크레딧 차감 (무제한이 아닌 경우)
        if current_user.credits != -1:
            current_user.credits -= 1
            remaining_credits = current_user.credits
        current_user.credits_used += 1
        
        # Webhook 발송 (백그라운드)
        webhook_url_to_use = webhook_url or current_user.webhook_url
        if webhook_url_to_use and current_user.webhook_enabled:
            background_tasks.add_task(
                webhook_sender.send_parsing_completed,
                webhook_url_to_use,
                request_id,
                response_data,
                f"/api/parse/{parse_record.id}",
                current_user.webhook_secret
            )
        
        logger.info(f"PDF 파싱 완료: {file.filename} - {parsed_data.get('unique_number', 'N/A')}")
        
        return ParseResponse(
            success=True,
            request_id=request_id,
            status="completed",
            data=response_data,
            is_demo=demo_mode,
            remaining_credits=remaining_credits
        )
        
    except Exception as e:
        logger.error(f"PDF 파싱 실패: {str(e)}")
        
        parse_record.status = ParseStatus.FAILED
        parse_record.error_message = str(e)
        
        # 실패 Webhook 발송
        webhook_url_to_use = webhook_url or current_user.webhook_url
        if webhook_url_to_use and current_user.webhook_enabled:
            background_tasks.add_task(
                webhook_sender.send_parsing_failed,
                webhook_url_to_use,
                request_id,
                str(e),
                current_user.webhook_secret
            )
        
        return ParseResponse(
            success=False,
            request_id=request_id,
            status="failed",
            error=str(e),
            is_demo=demo_mode,
            remaining_credits=remaining_credits
        )


@app.get("/api/parse/history", response_model=ParseHistoryResponse, tags=["PDF 파싱"])
async def get_parse_history(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_session)
):
    """파싱 기록 조회"""
    # 전체 개수
    count_result = await session.execute(
        select(func.count()).select_from(ParseRecord).where(
            ParseRecord.user_id == current_user.id
        )
    )
    total = count_result.scalar()
    
    # 목록 조회
    result = await session.execute(
        select(ParseRecord)
        .where(ParseRecord.user_id == current_user.id)
        .order_by(desc(ParseRecord.created_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    records = result.scalars().all()
    
    items = [
        ParseHistoryItem(
            id=r.id,
            file_name=r.file_name,
            status=r.status.value,
            unique_number=r.unique_number,
            property_address=r.property_address,
            section_a_count=r.section_a_count,
            section_b_count=r.section_b_count,
            created_at=r.created_at,
            completed_at=r.completed_at,
            processing_time=r.processing_time
        )
        for r in records
    ]
    
    return ParseHistoryResponse(
        success=True,
        items=items,
        total=total,
        page=page,
        page_size=page_size
    )


# ==================== 결제 API ====================

@app.get("/api/pricing", response_model=PricingResponse, tags=["결제"])
async def get_pricing():
    """요금제 목록 조회"""
    plans = [
        PlanInfo(
            type=plan_type,
            name=info["name"],
            price=info["price"],
            credits=info["credits"],
            features=info["features"]
        )
        for plan_type, info in settings.PRICING.items()
    ]
    
    return PricingResponse(plans=plans)


@app.get("/api/payment/client-key", tags=["결제"])
async def get_toss_client_key():
    """Toss Payments 클라이언트 키 조회 (프론트엔드 SDK용)"""
    return {"client_key": settings.TOSS_CLIENT_KEY}


@app.post("/api/payment/create", response_model=PaymentResponse, tags=["결제"])
async def create_payment(
    request: PaymentRequest,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_session)
):
    """결제 생성"""
    try:
        plan_type = PlanType(request.plan_type)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="유효하지 않은 요금제입니다."
        )
    
    payment_service = PaymentService()
    
    # 주문 생성
    order_data = await payment_service.create_order(
        user=current_user,
        plan_type=plan_type,
        success_url=request.success_url,
        fail_url=request.fail_url
    )
    
    # 결제 기록 생성
    plan_info = payment_service.get_plan_info(plan_type)
    payment = Payment(
        user_id=current_user.id,
        order_id=order_data["order_id"],
        plan_type=plan_type,
        plan_name=plan_info["name"],
        amount=order_data["amount"],
        status=PaymentStatus.PENDING
    )
    session.add(payment)
    
    return PaymentResponse(
        success=True,
        order_id=order_data["order_id"],
        order_name=order_data["order_name"],
        amount=order_data["amount"],
        plan_type=request.plan_type,
        customer_name=order_data["customer_name"],
        customer_email=order_data["customer_email"],
    )


@app.post("/api/payment/confirm", response_model=ResponseBase, tags=["결제"])
async def confirm_payment(
    request: PaymentConfirmRequest,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_session)
):
    """결제 승인 (Toss 콜백)"""
    # 결제 기록 조회
    result = await session.execute(
        select(Payment).where(Payment.order_id == request.order_id)
    )
    payment = result.scalar_one_or_none()
    
    if not payment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="결제 기록을 찾을 수 없습니다."
        )
    
    if payment.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="권한이 없습니다."
        )
    
    if payment.amount != request.amount:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="결제 금액이 일치하지 않습니다."
        )
    
    # Toss 결제 승인
    payment_service = PaymentService()
    try:
        confirm_data = await payment_service.confirm_order(
            payment_key=request.payment_key,
            order_id=request.order_id,
            amount=request.amount
        )
        
        # 결제 기록 업데이트
        payment.status = PaymentStatus.COMPLETED
        payment.payment_key = request.payment_key
        payment.method = confirm_data.get("method")
        payment.paid_at = datetime.utcnow()
        
        # 사용자 플랜 업데이트
        current_user.plan = payment.plan_type
        start_date, end_date = payment_service.calculate_plan_period(payment.plan_type)
        current_user.plan_start_date = start_date
        current_user.plan_end_date = end_date
        current_user.credits = payment_service.calculate_credits(payment.plan_type)
        
        logger.info(f"결제 완료: {current_user.email} - {payment.plan_type.value}")
        
        return ResponseBase(
            success=True,
            message="결제가 완료되었습니다."
        )
        
    except Exception as e:
        payment.status = PaymentStatus.FAILED
        logger.error(f"결제 승인 실패: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"결제 승인 실패: {str(e)}"
        )


@app.get("/api/payment/history", response_model=PaymentHistoryResponse, tags=["결제"])
async def get_payment_history(
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_session)
):
    """결제 내역 조회"""
    result = await session.execute(
        select(Payment)
        .where(Payment.user_id == current_user.id)
        .order_by(desc(Payment.created_at))
    )
    payments = result.scalars().all()
    
    items = [
        PaymentHistoryItem(
            id=p.id,
            order_id=p.order_id,
            plan_type=p.plan_type.value,
            plan_name=p.plan_name,
            amount=p.amount,
            status=p.status.value,
            method=p.method,
            created_at=p.created_at,
            paid_at=p.paid_at
        )
        for p in payments
    ]
    
    return PaymentHistoryResponse(
        success=True,
        items=items,
        total=len(items)
    )


# ==================== Webhook API ====================

@app.put("/api/webhook/settings", response_model=ResponseBase, tags=["Webhook"])
async def update_webhook_settings(
    request: WebhookSettingRequest,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_session)
):
    """Webhook 설정 업데이트"""
    current_user.webhook_enabled = request.enabled
    current_user.webhook_url = request.url
    current_user.webhook_secret = request.secret
    
    return ResponseBase(
        success=True,
        message="Webhook 설정이 업데이트되었습니다."
    )


# ==================== 사용자 설정 API ====================

@app.put("/api/user/settings", response_model=ResponseBase, tags=["사용자"])
async def update_user_settings(
    request: UserSettingsUpdate,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_session)
):
    """사용자 설정 업데이트"""
    if request.name:
        current_user.name = request.name
    if request.phone:
        current_user.phone = request.phone
    if request.company:
        current_user.company = request.company
    if request.webhook_enabled is not None:
        current_user.webhook_enabled = request.webhook_enabled
    if request.webhook_url:
        current_user.webhook_url = request.webhook_url
    if request.webhook_secret:
        current_user.webhook_secret = request.webhook_secret
    
    return ResponseBase(
        success=True,
        message="설정이 업데이트되었습니다."
    )


@app.post("/api/user/api-key/regenerate", tags=["사용자"])
async def regenerate_api_key(
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_session)
):
    """API 키 재발급"""
    current_user.api_key = generate_api_key()
    
    return {
        "success": True,
        "api_key": current_user.api_key
    }


# ==================== 헬스 체크 ====================

@app.get("/health", tags=["시스템"])
async def health_check():
    """헬스 체크"""
    return {
        "status": "healthy",
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION
    }


@app.get("/", tags=["시스템"])
async def root():
    """루트 엔드포인트"""
    return {
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs": "/docs",
        "health": "/health"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG
    )
