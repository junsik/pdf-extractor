"""공통 응답 스키마"""
from typing import Optional
from pydantic import BaseModel


class ResponseBase(BaseModel):
    success: bool = True
    message: Optional[str] = None
