"""PDF 처리 공통 유틸리티 (pdfplumber 기반)"""
import re
from typing import Optional


WATERMARK_RE = re.compile(r'열\s*람\s*용')


def is_watermark_char(obj: dict) -> bool:
    """pdfplumber 문자 객체가 워터마크인지 판별 (회색 색상 기반)"""
    if obj.get('object_type') != 'char':
        return False
    color = obj.get('non_stroking_color')
    if isinstance(color, (tuple, list)) and len(color) >= 3:
        return all(0.5 < c < 1.0 for c in color[:3])
    return False


def filter_watermark(page):
    """페이지에서 워터마크 문자를 제거한 필터링된 페이지 반환"""
    return page.filter(lambda obj: not is_watermark_char(obj))


def clean_text(text: Optional[str]) -> str:
    """텍스트 정리 (공백 정규화, 워터마크 제거)"""
    if not text:
        return ""
    text = WATERMARK_RE.sub('', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def clean_cell(cell: Optional[str]) -> str:
    """테이블 셀 정리"""
    if not cell:
        return ""
    return cell.strip()
