"""
Webhook 발송 시스템
"""
import hashlib
import hmac
import json
import asyncio
from datetime import datetime
from typing import Optional, Dict, Any
import httpx
from loguru import logger

from config import settings


class WebhookSender:
    """Webhook 발송 클래스"""
    
    def __init__(self):
        self.timeout = settings.WEBHOOK_TIMEOUT
        self.max_retries = settings.WEBHOOK_RETRY_COUNT
        self.secret = settings.WEBHOOK_SECRET
    
    def _generate_signature(self, payload: str) -> str:
        """HMAC 서명 생성"""
        return hmac.new(
            self.secret.encode(),
            payload.encode(),
            hashlib.sha256
        ).hexdigest()
    
    def _create_payload(
        self,
        event: str,
        request_id: str,
        data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Webhook 페이로드 생성"""
        timestamp = datetime.utcnow().isoformat()
        payload_data = {
            "event": event,
            "timestamp": timestamp,
            "data": {
                "request_id": request_id,
                "status": "success" if event == "parsing.completed" else "failed",
                **data
            }
        }
        
        # 서명 생성
        payload_str = json.dumps(payload_data, ensure_ascii=False)
        signature = self._generate_signature(payload_str)
        
        return {
            **payload_data,
            "signature": signature
        }
    
    async def send(
        self,
        url: str,
        event: str,
        request_id: str,
        data: Dict[str, Any],
        secret: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Webhook 발송
        
        Args:
            url: Webhook URL
            event: 이벤트 타입 (parsing.completed, parsing.failed)
            request_id: 요청 ID
            data: 전송할 데이터
            secret: 사용자 지정 시크릿 (없으면 기본 시크릿 사용)
        
        Returns:
            발송 결과
        """
        payload = self._create_payload(event, request_id, data)
        
        headers = {
            "Content-Type": "application/json",
            "X-Webhook-Signature": payload["signature"],
            "X-Webhook-Event": event,
            "X-Request-Id": request_id,
            "User-Agent": "RegistryPDFParser-Webhook/1.0"
        }
        
        # 사용자 지정 시크릿이 있으면 추가 서명
        if secret:
            custom_signature = hmac.new(
                secret.encode(),
                json.dumps(payload).encode(),
                hashlib.sha256
            ).hexdigest()
            headers["X-Custom-Signature"] = custom_signature
        
        result = {
            "url": url,
            "event": event,
            "success": False,
            "status_code": None,
            "response": None,
            "error": None,
            "retries": 0
        }
        
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for attempt in range(self.max_retries):
                try:
                    response = await client.post(
                        url,
                        json=payload,
                        headers=headers
                    )
                    
                    result["status_code"] = response.status_code
                    result["response"] = response.text[:1000]  # 응답 일부 저장
                    
                    if response.is_success:
                        result["success"] = True
                        logger.info(f"Webhook 발송 성공: {url} - {event}")
                        break
                    else:
                        result["error"] = f"HTTP {response.status_code}: {response.text[:200]}"
                        logger.warning(
                            f"Webhook 발송 실패 (시도 {attempt + 1}/{self.max_retries}): "
                            f"{url} - {result['error']}"
                        )
                        
                except httpx.TimeoutException:
                    result["error"] = "Timeout"
                    logger.warning(
                        f"Webhook 타임아웃 (시도 {attempt + 1}/{self.max_retries}): {url}"
                    )
                    
                except httpx.RequestError as e:
                    result["error"] = str(e)
                    logger.warning(
                        f"Webhook 요청 오류 (시도 {attempt + 1}/{self.max_retries}): {url} - {e}"
                    )
                
                result["retries"] = attempt + 1
                
                # 재시도 전 대기 (지수 백오프)
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
        
        if not result["success"]:
            logger.error(f"Webhook 발송 최종 실패: {url} - {result['error']}")
        
        return result
    
    async def send_parsing_completed(
        self,
        url: str,
        request_id: str,
        data: Dict[str, Any],
        download_url: Optional[str] = None,
        secret: Optional[str] = None
    ) -> Dict[str, Any]:
        """파싱 완료 Webhook 발송"""
        webhook_data = {
            "download_url": download_url,
            "parser_version": data.get("parser_version"),
            "summary": {
                "unique_number": data.get("unique_number"),
                "property_type": data.get("property_type"),
                "property_address": data.get("property_address"),
                "section_a_count": len(data.get("section_a", [])),
                "section_b_count": len(data.get("section_b", [])),
                "active_section_a_count": data.get("active_section_a_count", 0),
                "active_section_b_count": data.get("active_section_b_count", 0),
            }
        }
        
        return await self.send(
            url=url,
            event="parsing.completed",
            request_id=request_id,
            data=webhook_data,
            secret=secret
        )
    
    async def send_parsing_failed(
        self,
        url: str,
        request_id: str,
        error_message: str,
        secret: Optional[str] = None
    ) -> Dict[str, Any]:
        """파싱 실패 Webhook 발송"""
        return await self.send(
            url=url,
            event="parsing.failed",
            request_id=request_id,
            data={"error": error_message},
            secret=secret
        )


# 싱글톤 인스턴스
webhook_sender = WebhookSender()


async def send_webhook(
    url: str,
    event: str,
    request_id: str,
    data: Dict[str, Any],
    secret: Optional[str] = None
) -> Dict[str, Any]:
    """Webhook 발송 (편의 함수)"""
    return await webhook_sender.send(url, event, request_id, data, secret)
