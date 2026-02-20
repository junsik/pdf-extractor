"""상품(문서 파서) 도메인 엔티티"""
from dataclasses import dataclass
from typing import Optional

from domain.exceptions import ProductDisabledError


@dataclass
class ProductEntity:
    """파싱 가능한 문서 타입을 상품으로 관리"""
    id: str                      # "registry", "building_register"
    name: str                    # "등기부등본", "건축물대장"
    parser_key: str              # parsers/ 서브디렉토리명
    credit_cost: int = 1         # 건당 크레딧 소비량
    is_enabled: bool = True
    description: Optional[str] = None

    def ensure_enabled(self) -> None:
        """상품이 활성 상태인지 확인"""
        if not self.is_enabled:
            raise ProductDisabledError(self.id)
