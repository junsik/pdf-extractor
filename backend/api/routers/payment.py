"""결제 라우터"""
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from config import settings
from infrastructure.persistence.database import get_session
from infrastructure.persistence.models.user import User
from infrastructure.persistence.models.payment import Payment
from domain.enums import PlanType, PaymentStatus
from api.schemas.common import ResponseBase
from api.schemas.payment import (
    PlanInfo, PricingResponse, PaymentRequest, PaymentResponse,
    PaymentConfirmRequest, PaymentHistoryItem, PaymentHistoryResponse,
)
from api.dependencies import get_current_active_user
from infrastructure.payment.toss_gateway import PaymentService

router = APIRouter(tags=["결제"])


@router.get("/api/pricing", response_model=PricingResponse)
async def get_pricing():
    plans = [PlanInfo(type=pt, name=info["name"], price=info["price"],
                      credits=info["credits"], features=info["features"])
             for pt, info in settings.PRICING.items()]
    return PricingResponse(plans=plans)


@router.get("/api/payment/client-key")
async def get_toss_client_key():
    return {"client_key": settings.TOSS_CLIENT_KEY}


@router.post("/api/payment/create", response_model=PaymentResponse)
async def create_payment(request: PaymentRequest,
                         current_user: User = Depends(get_current_active_user),
                         session: AsyncSession = Depends(get_session)):
    try:
        plan_type = PlanType(request.plan_type)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="유효하지 않은 요금제입니다.")

    payment_service = PaymentService()
    order_data = await payment_service.create_order(user=current_user, plan_type=plan_type,
                                                     success_url=request.success_url, fail_url=request.fail_url)
    plan_info = payment_service.get_plan_info(plan_type)
    payment = Payment(user_id=current_user.id, order_id=order_data["order_id"],
                      plan_type=plan_type, plan_name=plan_info["name"],
                      amount=order_data["amount"], status=PaymentStatus.PENDING)
    session.add(payment)

    return PaymentResponse(success=True, order_id=order_data["order_id"], order_name=order_data["order_name"],
                           amount=order_data["amount"], plan_type=request.plan_type,
                           customer_name=order_data["customer_name"], customer_email=order_data["customer_email"])


@router.post("/api/payment/confirm", response_model=ResponseBase)
async def confirm_payment(request: PaymentConfirmRequest,
                          current_user: User = Depends(get_current_active_user),
                          session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(Payment).where(Payment.order_id == request.order_id))
    payment = result.scalar_one_or_none()
    if not payment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="결제 기록을 찾을 수 없습니다.")
    if payment.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="권한이 없습니다.")
    if payment.amount != request.amount:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="결제 금액이 일치하지 않습니다.")

    payment_service = PaymentService()
    try:
        confirm_data = await payment_service.confirm_order(
            payment_key=request.payment_key, order_id=request.order_id, amount=request.amount)
        payment.status = PaymentStatus.COMPLETED
        payment.payment_key = request.payment_key
        payment.method = confirm_data.get("method")
        payment.paid_at = datetime.utcnow()
        current_user.plan = payment.plan_type
        start_date, end_date = payment_service.calculate_plan_period(payment.plan_type)
        current_user.plan_start_date = start_date
        current_user.plan_end_date = end_date
        current_user.credits = payment_service.calculate_credits(payment.plan_type)
        logger.info(f"결제 완료: {current_user.email} - {payment.plan_type.value}")
        return ResponseBase(success=True, message="결제가 완료되었습니다.")
    except Exception as e:
        payment.status = PaymentStatus.FAILED
        logger.error(f"결제 승인 실패: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"결제 승인 실패: {str(e)}")


@router.get("/api/payment/history", response_model=PaymentHistoryResponse)
async def get_payment_history(current_user: User = Depends(get_current_active_user),
                              session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        select(Payment).where(Payment.user_id == current_user.id).order_by(desc(Payment.created_at)))
    payments = result.scalars().all()
    items = [PaymentHistoryItem(id=p.id, order_id=p.order_id, plan_type=p.plan_type.value,
                                 plan_name=p.plan_name, amount=p.amount, status=p.status.value,
                                 method=p.method, created_at=p.created_at, paid_at=p.paid_at)
             for p in payments]
    return PaymentHistoryResponse(success=True, items=items, total=len(items))
