"""
등기부등본 PDF 파서 템플릿

이 파일을 복사하여 새 파서 버전을 만드세요.
  cp parsers/registry/template.py parsers/registry/v2_0_0.py

BaseParser를 상속받아 구현해야 한다.

벤치마크:
  uv run python benchmark.py --parser v2.0.0
"""
import re
import io
import copy
from datetime import datetime
from typing import List, Optional, Dict, Any, Tuple

import pdfplumber

from parsers.base import BaseParser, DocumentTypeInfo, ParseResult
from parsers.common.pdf_utils import filter_watermark, clean_text, clean_cell, WATERMARK_RE
from parsers.common.text_utils import (
    parse_amount, parse_date_korean, extract_receipt_info,
    parse_resident_number, to_dict,
)
from parsers.common.cancellation import CancellationDetector


class RegistryParserV2(BaseParser):
    """등기부등본 파서 v2.0.0 — TODO: 구현"""

    @classmethod
    def document_type_info(cls) -> DocumentTypeInfo:
        return DocumentTypeInfo(
            type_id="registry",
            display_name="등기부등본",
            description="부동산 등기부등본 (토지, 건물, 집합건물)",
            sub_types=["land", "building", "aggregate_building"],
        )

    @classmethod
    def parser_version(cls) -> str:
        return "2.0.0"  # TODO: 버전 설정

    @classmethod
    def can_parse(cls, pdf_buffer: bytes, text_sample: str) -> float:
        """등기부등본 PDF인지 판별"""
        score = 0.0
        indicators = [
            ('고유번호', 0.3),
            ('표제부', 0.2),
            ('갑구', 0.2),
            ('을구', 0.1),
            ('등기부등본', 0.15),
        ]
        for keyword, weight in indicators:
            if keyword in text_sample:
                score += weight
        return min(score, 1.0)

    def parse(self, pdf_buffer: bytes) -> ParseResult:
        """PDF 파싱 실행"""
        # TODO: 구현
        return ParseResult(
            document_type="registry",
            document_sub_type="",
            parser_version=self.parser_version(),
            data={},
            raw_text="",
            errors=["파서 미구현"],
        )

    def mask_for_demo(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """데모 마스킹 — v1과 동일 로직 사용 가능"""
        return data
