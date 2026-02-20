"""Toss Payments API 클라이언트"""
import base64
import hashlib
import hmac
import uuid
from datetime import datetime, timedelta
from typing import Dict, Any
import httpx
from loguru import logger
from config import settings


class TossPayments:
    def __init__(self):
        self.client_key = settings.TOSS_CLIENT_KEY
        self.secret_key = settings.TOSS_SECRET_KEY
        self.api_url = settings.TOSS_API_URL

    def _get_headers(self) -> Dict[str, str]:
        encoded_secret = base64.b64encode(f"{self.secret_key}:".encode()).decode()
        return {"Authorization": f"Basic {encoded_secret}", "Content-Type": "application/json"}

    async def confirm_payment(self, payment_key: str, order_id: str, amount: int) -> Dict[str, Any]:
        url = f"{self.api_url}/payments/confirm"
        payload = {"paymentKey": payment_key, "orderId": order_id, "amount": amount}
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(url, headers=self._get_headers(), json=payload, timeout=30)
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as e:
                logger.error(f"Toss 결제 승인 실패: {e.response.text}")
                raise Exception(f"결제 승인 실패: {e.response.text}")

    async def get_payment(self, payment_key: str) -> Dict[str, Any]:
        url = f"{self.api_url}/payments/{payment_key}"
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(url, headers=self._get_headers(), timeout=30)
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as e:
                logger.error(f"Toss 결제 조회 실패: {e.response.text}")
                raise Exception(f"결제 조회 실패: {e.response.text}")

    async def cancel_payment(self, payment_key: str, cancel_reason: str) -> Dict[str, Any]:
        url = f"{self.api_url}/payments/{payment_key}/cancel"
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(url, headers=self._get_headers(), json={"cancelReason": cancel_reason}, timeout=30)
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as e:
                logger.error(f"Toss 결제 취소 실패: {e.response.text}")
                raise Exception(f"결제 취소 실패: {e.response.text}")

    @staticmethod
    def verify_signature(payload: str, signature: str) -> bool:
        expected = hmac.new(settings.TOSS_SECRET_KEY.encode(), payload.encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)


class PaymentService:
    def __init__(self):
        self.toss = TossPayments()

    @staticmethod
    def generate_order_id() -> str:
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        unique = uuid.uuid4().hex[:8]
        return f"ORD-{timestamp}-{unique}"

    def get_plan_info(self, plan_type) -> Dict[str, Any]:
        plan_value = plan_type.value if hasattr(plan_type, 'value') else plan_type
        return settings.PRICING.get(plan_value, {})

    async def create_order(self, user, plan_type, success_url: str, fail_url: str) -> Dict[str, Any]:
        plan_info = self.get_plan_info(plan_type)
        order_id = self.generate_order_id()
        return {
            "order_id": order_id,
            "amount": plan_info["price"],
            "order_name": f"등기부등본 파싱 서비스 - {plan_info['name']} 플랜",
            "plan_type": plan_type.value if hasattr(plan_type, 'value') else plan_type,
            "customer_name": user.name,
            "customer_email": user.email,
            "success_url": success_url,
            "fail_url": fail_url,
        }

    async def confirm_order(self, payment_key: str, order_id: str, amount: int) -> Dict[str, Any]:
        toss_response = await self.toss.confirm_payment(payment_key=payment_key, order_id=order_id, amount=amount)
        return {
            "payment_key": payment_key, "order_id": order_id, "amount": amount,
            "status": toss_response.get("status"), "method": toss_response.get("method"),
            "approved_at": toss_response.get("approvedAt"),
            "card": toss_response.get("card", {}), "receipt": toss_response.get("receipt", {}),
        }

    def calculate_credits(self, plan_type) -> int:
        return self.get_plan_info(plan_type).get("credits", 0)

    def calculate_plan_period(self, plan_type) -> tuple:
        start_date = datetime.now()
        return start_date, start_date + timedelta(days=30)
