"""
등기부등본 PDF 파서 템플릿

이 파일을 복사하여 새 파서 버전을 만드세요.
  cp parsers/template.py parsers/v3_0_0.py

인터페이스 계약:
  - PARSER_VERSION: str
  - parse_registry_pdf(pdf_buffer: bytes) -> Dict[str, Any]

출력 스키마: schemas.RegistryData

벤치마크:
  uv run python benchmark.py --parser v3.0.0
"""
import re
import io
from datetime import datetime
from typing import List, Optional, Dict, Any, Tuple

import pdfplumber

# ==================== 버전 ====================

PARSER_VERSION = "3.0.0"  # TODO: 버전 설정


# ==================== 외부 인터페이스 ====================

def parse_registry_pdf(pdf_buffer: bytes) -> Dict[str, Any]:
    """
    PDF 파싱 실행.

    Args:
        pdf_buffer: PDF 파일의 raw bytes

    Returns:
        schemas.RegistryData 스키마를 만족하는 dict
    """
    with pdfplumber.open(io.BytesIO(pdf_buffer)) as pdf:

        # ── 1. 전체 텍스트 추출 ──
        raw_text = ""
        for page in pdf.pages:
            text = page.extract_text() or ""
            raw_text += text + "\n"

        # ── 2. 기본 정보 ──
        unique_number = _extract_unique_number(raw_text)
        property_type = _detect_property_type(raw_text)
        property_address = _extract_address(raw_text)

        # ── 3. 표제부 파싱 ──
        title_info = _parse_title(pdf, property_type)
        title_info["unique_number"] = unique_number
        title_info["property_type"] = property_type
        title_info["address"] = property_address

        # ── 4. 갑구 파싱 ──
        section_a = _parse_section_a(pdf)

        # ── 5. 을구 파싱 ──
        section_b = _parse_section_b(pdf)

    # ── 6. 통계 ──
    result = {
        "unique_number": unique_number,
        "property_type": property_type,
        "property_address": property_address,
        "title_info": title_info,
        "section_a": section_a,
        "section_b": section_b,
        "raw_text": raw_text,
        "parse_date": datetime.now().isoformat(),
        "parser_version": PARSER_VERSION,
        "errors": [],
        "section_a_count": len(section_a),
        "section_b_count": len(section_b),
        "active_section_a_count": sum(
            1 for e in section_a if not e.get("is_cancelled")
        ),
        "active_section_b_count": sum(
            1 for e in section_b if not e.get("is_cancelled")
        ),
    }

    return result


# ==================== 기본 정보 추출 ====================

def _extract_unique_number(text: str) -> str:
    """고유번호 추출"""
    match = re.search(r"고유번호\s*([\d-]+)", text)
    return match[1] if match else ""


def _detect_property_type(text: str) -> str:
    """부동산 유형 감지: land | building | aggregate_building"""
    first = text[:500]
    if "- 토지 -" in first or "[토지]" in first:
        return "land"
    if "- 집합건물 -" in first or "[집합건물]" in first:
        return "aggregate_building"
    return "building"


def _extract_address(text: str) -> str:
    """소재지 주소 추출"""
    match = re.search(r"\[(?:토지|건물|집합건물)\]\s*([^\n]+)", text)
    if match:
        return match[1].strip()
    return ""


# ==================== 표제부 ====================

def _parse_title(pdf, property_type: str) -> Dict[str, Any]:
    """
    표제부 파싱.

    TODO: 구현
    - 토지: land_entries, land_type, land_area
    - 건물: building_entries, structure, roof_type, floors, areas
    - 집합건물: 위 + exclusive_part_entries, land_right_entries, land_right_ratio_entries
    """
    return {
        "unique_number": "",
        "property_type": "",
        "address": "",
        "road_address": None,
        "building_name": None,
        "structure": None,
        "roof_type": None,
        "floors": None,
        "building_type": None,
        "areas": [],
        "land_right_ratio": None,
        "exclusive_area": None,
        "total_floor_area": 0.0,
        "land_type": None,
        "land_area": None,
        "land_entries": [],
        "building_entries": [],
        "exclusive_part_entries": [],
        "land_right_entries": [],
        "land_right_ratio_entries": [],
    }


# ==================== 갑구 ====================

def _parse_section_a(pdf) -> List[Dict[str, Any]]:
    """
    갑구 (소유권에 관한 사항) 파싱.

    TODO: 구현
    - 순위번호, 등기목적, 접수일자/번호, 등기원인
    - 소유자 (이름, 주민번호, 주소, 지분)
    - 채권자, 청구금액 (가압류 등)
    - 말소 감지 (붉은 선/글자)
    - 말소 관계 매핑 (cancels_rank_number)

    각 항목은 schemas.SectionAEntry 구조를 따름.
    """
    entries = []

    # TODO: 테이블 추출 + 파싱 로직

    return entries


# ==================== 을구 ====================

def _parse_section_b(pdf) -> List[Dict[str, Any]]:
    """
    을구 (소유권 이외의 권리) 파싱.

    TODO: 구현
    - 근저당권: max_claim_amount, debtor, mortgagee
    - 임차권/전세권: deposit_amount, monthly_rent, lessee, lease_term
    - 지상권: purpose, scope, duration
    - 말소 감지 + 관계 매핑

    각 항목은 schemas.SectionBEntry 구조를 따름.
    """
    entries = []

    # TODO: 테이블 추출 + 파싱 로직

    return entries
