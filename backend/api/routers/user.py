"""사용자 설정 + Webhook 라우터"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.persistence.database import get_session
from infrastructure.persistence.models.user import User
from api.schemas.common import ResponseBase
from api.schemas.user import UserSettingsUpdate, WebhookSettingRequest
from api.dependencies import get_current_active_user
from infrastructure.auth.password_service import generate_api_key

router = APIRouter(tags=["사용자"])


@router.put("/api/webhook/settings", response_model=ResponseBase)
async def update_webhook_settings(request: WebhookSettingRequest,
                                   current_user: User = Depends(get_current_active_user),
                                   session: AsyncSession = Depends(get_session)):
    current_user.webhook_enabled = request.enabled
    current_user.webhook_url = request.url
    current_user.webhook_secret = request.secret
    return ResponseBase(success=True, message="Webhook 설정이 업데이트되었습니다.")


@router.put("/api/user/settings", response_model=ResponseBase)
async def update_user_settings(request: UserSettingsUpdate,
                                current_user: User = Depends(get_current_active_user),
                                session: AsyncSession = Depends(get_session)):
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
    return ResponseBase(success=True, message="설정이 업데이트되었습니다.")


@router.post("/api/user/api-key/regenerate")
async def regenerate_api_key(current_user: User = Depends(get_current_active_user),
                             session: AsyncSession = Depends(get_session)):
    current_user.api_key = generate_api_key()
    return {"success": True, "api_key": current_user.api_key}
