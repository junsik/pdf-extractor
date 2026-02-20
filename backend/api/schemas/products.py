"""상품(문서 파서 타입) 스키마"""
from typing import Optional, List
from pydantic import BaseModel


class ProductInfo(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    credit_cost: int = 1
    is_enabled: bool = True
    available_versions: List[str] = []


class ProductListResponse(BaseModel):
    products: List[ProductInfo]
