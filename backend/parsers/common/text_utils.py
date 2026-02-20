"""텍스트 파싱 공통 유틸리티"""
import re
from typing import Optional, Tuple


def parse_amount(text: str) -> Optional[int]:
    """금액 문자열을 숫자로 변환 (원정 변형 포함)"""
    if not text:
        return None
    match = re.search(r'금\s*([\d,]+)\s*원정?', text)
    if match:
        return int(match[1].replace(',', ''))
    return None


def parse_date_korean(text: str) -> Optional[str]:
    """한국어 날짜 형식 파싱 (YYYY년MM월DD일, YYYY.MM.DD, YYYY-MM-DD)"""
    if not text:
        return None
    # 한국어 형식
    match = re.search(r'(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일', text)
    if match:
        return f"{match[1]}년 {match[2].zfill(2)}월 {match[3].zfill(2)}일"
    # 점 구분 형식 (2025.01.03)
    match = re.search(r'(\d{4})\.(\d{1,2})\.(\d{1,2})', text)
    if match:
        return f"{match[1]}년 {match[2].zfill(2)}월 {match[3].zfill(2)}일"
    # ISO 형식 (2025-01-03)
    match = re.search(r'(\d{4})-(\d{1,2})-(\d{1,2})', text)
    if match:
        return f"{match[1]}년 {match[2].zfill(2)}월 {match[3].zfill(2)}일"
    return None


def extract_receipt_info(text: str) -> Tuple[str, str]:
    """접수일자와 접수번호 추출 (셀 텍스트에서)"""
    date_str = ""
    number_str = ""
    # 한국어 형식 우선
    date_match = re.search(r'(\d{4}년\s*\d{1,2}월\s*\d{1,2}일)', text)
    if date_match:
        date_str = date_match[1]
    else:
        # 점 구분 형식 (2025.01.03)
        date_match = re.search(r'(\d{4}\.\d{1,2}\.\d{1,2})', text)
        if date_match:
            date_str = date_match[1]
        else:
            # ISO 형식 (2025-01-03)
            date_match = re.search(r'(\d{4}-\d{1,2}-\d{1,2})', text)
            if date_match:
                date_str = date_match[1]
    number_match = re.search(r'제?\s*([\d]+호)', text)
    if number_match:
        number_str = number_match[1]
    return date_str, number_str


def parse_resident_number(text: str) -> Optional[str]:
    """주민등록번호/법인번호 추출 (*, ○ 마스킹 대응)"""
    # 개인: 6자리-7자리(마스킹 포함: *, ○, ● 등)
    match = re.search(r'(\d{6})-([*○●]{7}|\d{7}|\d{1,6}[*○●]+)', text)
    if match:
        return f"{match[1]}-{match[2]}"
    # 법인: 6자리-7자리
    match = re.search(r'(\d{6})-(\d{7})', text)
    if match:
        return f"{match[1]}-{match[2]}"
    # 법인: 000-00-00000
    match = re.search(r'(\d{3}-\d{2}-\d{5})', text)
    if match:
        return match[1]
    return None


def to_dict(obj):
    """데이터클래스를 딕셔너리로 변환"""
    if hasattr(obj, '__dataclass_fields__'):
        d = {}
        for k in obj.__dataclass_fields__:
            val = getattr(obj, k)
            d[k] = to_dict(val)
        return d
    elif isinstance(obj, list):
        return [to_dict(item) for item in obj]
    elif isinstance(obj, dict):
        return {k: to_dict(v) for k, v in obj.items()}
    else:
        return obj
