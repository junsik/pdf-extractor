"""파싱 기록 Repository 인터페이스"""
from abc import ABC, abstractmethod
from typing import List, Tuple, Dict, Any


class ParseRecordRepository(ABC):
    @abstractmethod
    async def create(self, user_id: int, file_name: str, file_size: int,
                     document_type: str = "registry") -> int: ...
    @abstractmethod
    async def update_completed(self, record_id: int, result_data: dict,
                                processing_time: float, parser_version: str = "") -> None: ...
    @abstractmethod
    async def update_failed(self, record_id: int, error: str) -> None: ...
    @abstractmethod
    async def count_today(self, user_id: int) -> int: ...
    @abstractmethod
    async def list_by_user(self, user_id: int, page: int = 1,
                           page_size: int = 20) -> Tuple[List[Dict[str, Any]], int]: ...
