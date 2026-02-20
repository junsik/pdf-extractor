"""
FastAPI 의존성 주입 (Depends)

모든 라우터에서 사용하는 공통 의존성을 정의한다.
"""
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from infrastructure.persistence.database import get_session
from infrastructure.persistence.models.user import User
from domain.enums import UserRole
from infrastructure.auth.jwt_service import decode_token

security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    session: AsyncSession = Depends(get_session)
) -> User:
    """현재 인증된 사용자 반환"""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="유효하지 않은 인증 정보입니다.",
        headers={"WWW-Authenticate": "Bearer"},
    )

    token = credentials.credentials
    payload = decode_token(token)

    if payload is None or payload.get("type") != "access":
        raise credentials_exception

    user_id_raw = payload.get("sub")
    if user_id_raw is None:
        raise credentials_exception
    try:
        user_id = int(user_id_raw)
    except (ValueError, TypeError):
        raise credentials_exception

    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if user is None:
        raise credentials_exception

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="비활성화된 계정입니다.")
    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user)
) -> User:
    """활성 사용자 확인"""
    if not current_user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="비활성화된 계정입니다.")
    return current_user


async def get_admin_user(
    current_user: User = Depends(get_current_user)
) -> User:
    """관리자 사용자 확인"""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="관리자 권한이 필요합니다.")
    return current_user
