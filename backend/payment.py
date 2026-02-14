"""
결제 시스템 - Toss Payments 연동
"""
import hashlib
import hmac
import json
import uuid
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import httpx
from loguru import logger

from config import settings
from models import Payment, PaymentStatus, PlanType, User


class TossPayments:
    """Toss Payments API 클라이언트"""
    
    def __init__(self):
        self.client_key = settings.TOSS_CLIENT_KEY
        self.secret_key = settings.TOSS_SECRET_KEY
        self.api_url = settings.TOSS_API_URL
    
    def _get_headers(self) -> Dict[str, str]:
        """API 요청 헤더 생성"""
        # Toss API는 시크릿 키를 Base64 인코딩
        import base64
        encoded_secret = base64.b64encode(f"{self.secret_key}:".encode()).decode()
        return {
            "Authorization": f"Basic {encoded_secret}",
            "Content-Type": "application/json"
        }
    
    async def create_payment(
        self,
        order_id: str,
        amount: int,
        order_name: str,
        success_url: str,
        fail_url: str
    ) -> Dict[str, Any]:
        """결제 생성"""
        url = f"{self.api_url}/payments"
        
        payload = {
            "method": "CARD",  # 기본 결제수단: 카드
            "orderId": order_id,
            "amount": amount,
            "orderName": order_name,
            "successUrl": success_url,
            "failUrl": fail_url,
            "customerName": "고객",
        }
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    url,
                    headers=self._get_headers(),
                    json=payload,
                    timeout=30
                )
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as e:
                logger.error(f"Toss 결제 생성 실패: {e.response.text}")
                raise Exception(f"결제 생성 실패: {e.response.text}")
    
    async def confirm_payment(
        self,
        payment_key: str,
        order_id: str,
        amount: int
    ) -> Dict[str, Any]:
        """결제 승인"""
        url = f"{self.api_url}/payments/confirm"

        payload = {
            "paymentKey": payment_key,
            "orderId": order_id,
            "amount": amount
        }
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    url,
                    headers=self._get_headers(),
                    json=payload,
                    timeout=30
                )
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as e:
                logger.error(f"Toss 결제 승인 실패: {e.response.text}")
                raise Exception(f"결제 승인 실패: {e.response.text}")
    
    async def get_payment(self, payment_key: str) -> Dict[str, Any]:
        """결제 조회"""
        url = f"{self.api_url}/payments/{payment_key}"
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    url,
                    headers=self._get_headers(),
                    timeout=30
                )
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as e:
                logger.error(f"Toss 결제 조회 실패: {e.response.text}")
                raise Exception(f"결제 조회 실패: {e.response.text}")
    
    async def cancel_payment(
        self,
        payment_key: str,
        cancel_reason: str
    ) -> Dict[str, Any]:
        """결제 취소"""
        url = f"{self.api_url}/payments/{payment_key}/cancel"
        
        payload = {
            "cancelReason": cancel_reason
        }
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    url,
                    headers=self._get_headers(),
                    json=payload,
                    timeout=30
                )
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as e:
                logger.error(f"Toss 결제 취소 실패: {e.response.text}")
                raise Exception(f"결제 취소 실패: {e.response.text}")
    
    @staticmethod
    def verify_signature(payload: str, signature: str) -> bool:
        """웹훅 서명 검증"""
        expected = hmac.new(
            settings.TOSS_SECRET_KEY.encode(),
            payload.encode(),
            hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected, signature)


class PaymentService:
    """결제 서비스"""
    
    def __init__(self):
        self.toss = TossPayments()
    
    @staticmethod
    def generate_order_id() -> str:
        """주문번호 생성"""
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        unique = uuid.uuid4().hex[:8]
        return f"ORD-{timestamp}-{unique}"
    
    def get_plan_info(self, plan_type: PlanType) -> Dict[str, Any]:
        """요금제 정보 조회"""
        return settings.PRICING.get(plan_type.value, {})
    
    async def create_order(
        self,
        user: User,
        plan_type: PlanType,
        success_url: str,
        fail_url: str
    ) -> Dict[str, Any]:
        """주문 생성 (주문 정보만 반환, 결제는 프론트엔드 Toss SDK에서 처리)"""
        plan_info = self.get_plan_info(plan_type)

        order_id = self.generate_order_id()
        amount = plan_info["price"]
        order_name = f"등기부등본 파싱 서비스 - {plan_info['name']} 플랜"

        return {
            "order_id": order_id,
            "amount": amount,
            "order_name": order_name,
            "plan_type": plan_type.value,
            "customer_name": user.name,
            "customer_email": user.email,
            "success_url": success_url,
            "fail_url": fail_url,
        }
    
    async def confirm_order(
        self,
        payment_key: str,
        order_id: str,
        amount: int
    ) -> Dict[str, Any]:
        """결제 승인"""
        # Toss 결제 승인
        toss_response = await self.toss.confirm_payment(
            payment_key=payment_key,
            order_id=order_id,
            amount=amount
        )
        
        return {
            "payment_key": payment_key,
            "order_id": order_id,
            "amount": amount,
            "status": toss_response.get("status"),
            "method": toss_response.get("method"),
            "approved_at": toss_response.get("approvedAt"),
            "card": toss_response.get("card", {}),
            "receipt": toss_response.get("receipt", {})
        }
    
    def calculate_credits(self, plan_type: PlanType) -> int:
        """플랜별 크레딧 계산"""
        plan_info = self.get_plan_info(plan_type)
        credits = plan_info.get("credits", 0)
        return credits  # -1이면 무제한
    
    def calculate_plan_period(self, plan_type: PlanType) -> tuple:
        """플랜 기간 계산"""
        start_date = datetime.now()
        end_date = start_date + timedelta(days=30)  # 30일
        return start_date, end_date
