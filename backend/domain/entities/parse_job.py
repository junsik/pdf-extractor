"""파싱 작업 값 객체"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class ParseJob:
    """단일 파싱 요청을 나타내는 값 객체"""
    user_id: int
    document_type: str
    file_name: str
    file_size: int
    demo_mode: bool = False
    parser_version: str = "latest"
    webhook_url: Optional[str] = None
    request_id: str = ""
    created_at: datetime = field(default_factory=datetime.utcnow)
