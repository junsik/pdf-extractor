"""Webhook 포트 인터페이스"""
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any


class WebhookPort(ABC):
    @abstractmethod
    async def send_parsing_completed(self, url: str, request_id: str, data: Dict[str, Any],
                                     download_url: Optional[str] = None,
                                     secret: Optional[str] = None) -> Dict[str, Any]: ...
    @abstractmethod
    async def send_parsing_failed(self, url: str, request_id: str, error_message: str,
                                  secret: Optional[str] = None) -> Dict[str, Any]: ...
