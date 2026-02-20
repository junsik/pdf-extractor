"""Webhook 발송 시스템"""
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
    def __init__(self):
        self.timeout = settings.WEBHOOK_TIMEOUT
        self.max_retries = settings.WEBHOOK_RETRY_COUNT
        self.secret = settings.WEBHOOK_SECRET

    def _generate_signature(self, payload: str) -> str:
        return hmac.new(self.secret.encode(), payload.encode(), hashlib.sha256).hexdigest()

    def _create_payload(self, event: str, request_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        timestamp = datetime.utcnow().isoformat()
        payload_data = {"event": event, "timestamp": timestamp,
                        "data": {"request_id": request_id,
                                 "status": "success" if event == "parsing.completed" else "failed", **data}}
        payload_str = json.dumps(payload_data, ensure_ascii=False)
        return {**payload_data, "signature": self._generate_signature(payload_str)}

    async def send(self, url: str, event: str, request_id: str, data: Dict[str, Any],
                   secret: Optional[str] = None) -> Dict[str, Any]:
        payload = self._create_payload(event, request_id, data)
        headers = {"Content-Type": "application/json", "X-Webhook-Signature": payload["signature"],
                    "X-Webhook-Event": event, "X-Request-Id": request_id,
                    "User-Agent": "RegistryPDFParser-Webhook/1.0"}
        if secret:
            headers["X-Custom-Signature"] = hmac.new(
                secret.encode(), json.dumps(payload).encode(), hashlib.sha256).hexdigest()

        result = {"url": url, "event": event, "success": False,
                  "status_code": None, "response": None, "error": None, "retries": 0}

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for attempt in range(self.max_retries):
                try:
                    response = await client.post(url, json=payload, headers=headers)
                    result["status_code"] = response.status_code
                    result["response"] = response.text[:1000]
                    if response.is_success:
                        result["success"] = True
                        logger.info(f"Webhook 발송 성공: {url} - {event}")
                        break
                    result["error"] = f"HTTP {response.status_code}: {response.text[:200]}"
                except httpx.TimeoutException:
                    result["error"] = "Timeout"
                except httpx.RequestError as e:
                    result["error"] = str(e)
                result["retries"] = attempt + 1
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
        if not result["success"]:
            logger.error(f"Webhook 발송 최종 실패: {url} - {result['error']}")
        return result

    async def send_parsing_completed(self, url: str, request_id: str, data: Dict[str, Any],
                                     download_url: Optional[str] = None,
                                     secret: Optional[str] = None) -> Dict[str, Any]:
        webhook_data = {"download_url": download_url, "parser_version": data.get("parser_version"),
                        "summary": {"unique_number": data.get("unique_number"),
                                    "property_type": data.get("property_type"),
                                    "property_address": data.get("property_address"),
                                    "section_a_count": len(data.get("section_a", [])),
                                    "section_b_count": len(data.get("section_b", [])),
                                    "active_section_a_count": data.get("active_section_a_count", 0),
                                    "active_section_b_count": data.get("active_section_b_count", 0)}}
        return await self.send(url=url, event="parsing.completed", request_id=request_id,
                               data=webhook_data, secret=secret)

    async def send_parsing_failed(self, url: str, request_id: str, error_message: str,
                                  secret: Optional[str] = None) -> Dict[str, Any]:
        return await self.send(url=url, event="parsing.failed", request_id=request_id,
                               data={"error": error_message}, secret=secret)


webhook_sender = WebhookSender()


async def send_webhook(url: str, event: str, request_id: str, data: Dict[str, Any],
                       secret: Optional[str] = None) -> Dict[str, Any]:
    return await webhook_sender.send(url, event, request_id, data, secret)
