"""
파서 플러그인 시스템 기반 클래스

모든 문서 파서는 BaseParser를 상속받아야 한다.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Any, List, Optional, Type


@dataclass
class DocumentTypeInfo:
    """파서 플러그인이 처리하는 문서 타입 메타데이터"""
    type_id: str              # "registry", "building_register"
    display_name: str         # "등기부등본", "건축물대장"
    description: str          # 문서 설명
    sub_types: List[str] = field(default_factory=list)  # ["land", "building", ...]


@dataclass
class ParseResult:
    """모든 파서의 공통 출력 래퍼"""
    document_type: str              # "registry"
    document_sub_type: str = ""     # "aggregate_building"
    parser_version: str = ""
    parse_date: str = field(default_factory=lambda: datetime.now().isoformat())
    data: Dict[str, Any] = field(default_factory=dict)
    raw_text: str = ""
    errors: List[str] = field(default_factory=list)
    confidence: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)


class BaseParser(ABC):
    """문서 파서 플러그인 기반 클래스"""

    @classmethod
    @abstractmethod
    def document_type_info(cls) -> DocumentTypeInfo:
        """이 파서가 처리하는 문서 타입 정보"""
        ...

    @classmethod
    @abstractmethod
    def parser_version(cls) -> str:
        """파서 버전 문자열 (예: '1.0.0')"""
        ...

    @classmethod
    @abstractmethod
    def can_parse(cls, pdf_buffer: bytes, text_sample: str) -> float:
        """이 PDF를 파싱할 수 있는지 판별.

        Args:
            pdf_buffer: PDF 파일의 첫 10KB
            text_sample: 추출된 텍스트의 첫 2000자

        Returns:
            0.0~1.0 confidence 점수. 0.0이면 처리 불가.
        """
        ...

    @abstractmethod
    def parse(self, pdf_buffer: bytes) -> ParseResult:
        """PDF 전체를 파싱하여 구조화된 결과 반환"""
        ...

    def mask_for_demo(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """데모 모드용 PII 마스킹. 파서별로 오버라이드."""
        return data
