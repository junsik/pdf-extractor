"""인증 라우터"""
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from config import settings
from infrastructure.persistence.database import get_session
from infrastructure.persistence.models.user import User
from domain.enums import UserRole, PlanType
from api.schemas.common import ResponseBase
from api.schemas.auth import (
    UserSignupRequest, UserLoginRequest, TokenResponse, UserResponse,
)
from api.dependencies import get_current_active_user
from infrastructure.auth.password_service import hash_password, verify_password, generate_api_key
from infrastructure.auth.jwt_service import create_access_token, create_refresh_token

router = APIRouter(prefix="/api/auth", tags=["인증"])


@router.post("/signup", response_model=ResponseBase)
async def signup(request: UserSignupRequest, session: AsyncSession = Depends(get_session)):
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                        detail="현재 회원가입이 일시 중단되었습니다. 나중에 다시 시도해주세요.")

    result = await session.execute(select(User).where(User.email == request.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="이미 등록된 이메일입니다.")

    user = User(email=request.email, password_hash=hash_password(request.password),
                name=request.name, phone=request.phone, company=request.company,
                role=UserRole.USER, plan=PlanType.FREE,
                credits=settings.PRICING["free"]["credits"], api_key=generate_api_key())
    session.add(user)
    await session.flush()
    logger.info(f"새 사용자 가입: {user.email}")
    return ResponseBase(success=True, message="회원가입이 완료되었습니다.")


@router.post("/login", response_model=TokenResponse)
async def login(request: UserLoginRequest, session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(User).where(User.email == request.email))
    user = result.scalar_one_or_none()

    if not user or not verify_password(request.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="이메일 또는 비밀번호가 올바르지 않습니다.")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="비활성화된 계정입니다.")

    user.last_login_at = datetime.utcnow()
    access_token = create_access_token({"sub": user.id})
    refresh_token = create_refresh_token({"sub": user.id})
    logger.info(f"사용자 로그인: {user.email}")
    return TokenResponse(access_token=access_token, refresh_token=refresh_token,
                         expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60)


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_active_user)):
    return UserResponse(
        id=current_user.id, email=current_user.email, name=current_user.name,
        phone=current_user.phone, company=current_user.company,
        role=current_user.role.value, plan=current_user.plan.value,
        plan_end_date=current_user.plan_end_date, credits=current_user.credits,
        credits_used=current_user.credits_used, webhook_enabled=current_user.webhook_enabled,
        webhook_url=current_user.webhook_url, api_key=current_user.api_key,
        created_at=current_user.created_at)
