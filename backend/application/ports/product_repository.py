"""상품 Repository 인터페이스"""
from abc import ABC, abstractmethod
from typing import Optional, List
from domain.entities.product import ProductEntity


class ProductRepository(ABC):
    @abstractmethod
    async def get_by_id(self, product_id: str) -> Optional[ProductEntity]: ...
    @abstractmethod
    async def list_enabled(self) -> List[ProductEntity]: ...
    @abstractmethod
    async def upsert(self, product: ProductEntity) -> None: ...
