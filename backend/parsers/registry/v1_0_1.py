"""
등기부등본 PDF 파싱 엔진 v1.0.1
- pdfplumber 테이블 기반 추출 (텍스트 + 구조 동시 파싱)
- 붉은 선/글자 기반 말소사항 감지
- 페이지 간 테이블 연결
- 토지 / 건물 / 집합건물 지원

v1.0.0 대비 개선사항:
- TABLE_SETTINGS로 테이블 추출 파라미터 최적화
- 섹션 패턴: '표제부' optional 처리, 주요 등기사항 요약 파싱 추가
- _classify_table_by_columns: 컬럼 기반 섹션 분류 (표 제목이 표 밖에 있는 경우 대응)
- _detect_section_near_table: 테이블 상단 텍스트 기반 섹션 감지
- _strip_watermark_fragments_in_row: 행 단위 워터마크 분절 처리
- _merge_continuation_rows: 타 섹션 헤더 오염 방지 필터 추가
- _parse_title_land: 컬럼 수 유연성 처리
- parse_warnings / parse_stats: 파싱 품질 메타 수집
- 섹션 기반 property_type 보정 로직
"""
from __future__ import annotations
import re
import io
import copy
import base64
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime
from dataclasses import dataclass, field
from loguru import logger
import pdfplumber

from parsers.base import BaseParser, DocumentTypeInfo, ParseResult
from parsers.common.pdf_utils import filter_watermark, clean_text, clean_cell, WATERMARK_RE
from parsers.common.text_utils import (
    parse_amount, parse_date_korean, extract_receipt_info,
    parse_resident_number, to_dict,
)
from parsers.common.cancellation import CancellationDetector


# ==================== 데이터 클래스 ====================

@dataclass
class FloorArea:
    floor: str                  # 층 정보 (예: '1층', '지하1층')
    area: float                 # 면적 (㎡)
    is_excluded: bool = False   # 제외 면적 여부


@dataclass
class OwnerInfo:
    name: str                               # 성명 또는 법인명
    resident_number: Optional[str] = None  # 주민/법인등록번호 (마스킹 포함, 예: '650603-*******')
    address: Optional[str] = None          # 주소
    share: Optional[str] = None            # 지분 (공유 시, 예: '3분의 1'). 단독소유는 None
    role: Optional[str] = None             # 등기부상 역할: '소유자' | '공유자' | '가등기권자' | '수탁자'


@dataclass
class CreditorInfo:
    name: str                               # 채권자 성명 또는 법인명
    resident_number: Optional[str] = None  # 주민/법인등록번호
    address: Optional[str] = None          # 주소


@dataclass
class LesseeInfo:
    name: str                               # 임차인 성명
    resident_number: Optional[str] = None  # 주민등록번호
    address: Optional[str] = None          # 주소


@dataclass
class LeaseTermInfo:
    contract_date: Optional[str] = None                # 계약일자
    resident_registration_date: Optional[str] = None   # 주민등록일자
    possession_start_date: Optional[str] = None        # 점유개시일
    fixed_date: Optional[str] = None                   # 확정일자


@dataclass
class LandTitleEntry:
    """표제부 — 토지의 표시 항목"""
    display_number: str = ""    # 표시번호
    receipt_date: str = ""      # 접수일자
    location: str = ""          # 소재지번
    land_type: str = ""         # 지목 (예: '대', '전', '답')
    area: str = ""              # 면적
    cause_and_other: str = ""   # 등기원인 및 기타사항
    is_cancelled: bool = False  # 말소 여부


@dataclass
class BuildingTitleEntry:
    """표제부 — 건물의 표시 항목"""
    display_number: str = ""        # 표시번호
    receipt_date: str = ""          # 접수일자
    location_or_number: str = ""    # 소재지번 또는 건물번호
    building_detail: str = ""       # 건물내역 (구조·용도·면적)
    cause_and_other: str = ""       # 등기원인 및 기타사항
    is_cancelled: bool = False      # 말소 여부


@dataclass
class LandRightEntry:
    """대지권의 목적인 토지의 표시"""
    display_number: str = ""    # 표시번호
    location: str = ""          # 소재지번
    land_type: str = ""         # 지목
    area: str = ""              # 면적
    cause_and_other: str = ""   # 등기원인 및 기타사항


@dataclass
class ExclusivePartEntry:
    """전유부분의 건물의 표시 (집합건물)"""
    display_number: str = ""    # 표시번호
    receipt_date: str = ""      # 접수일자
    building_number: str = ""   # 건물번호 (동·호)
    building_detail: str = ""   # 건물내역
    cause_and_other: str = ""   # 등기원인 및 기타사항
    is_cancelled: bool = False  # 말소 여부


@dataclass
class LandRightRatioEntry:
    """대지권의 표시"""
    display_number: str = ""        # 표시번호
    land_right_type: str = ""       # 대지권 종류 (예: '소유권')
    land_right_ratio: str = ""      # 대지권 비율 (예: '15300분의 34.56')
    cause_and_other: str = ""       # 등기원인 및 기타사항
    is_cancelled: bool = False      # 말소 여부


@dataclass
class SectionAEntry:
    """갑구 항목 — 소유권에 관한 사항"""
    rank_number: str            # 순위번호 (예: '1', '1-1', '2'). 부기등기는 '-'로 구분
    registration_type: str      # 등기목적 (예: '소유권이전', '소유권이전청구권가등기', '등기명의인표시변경')
    receipt_date: str = ""      # 접수일자 (예: '2007년9월11일')
    receipt_number: str = ""    # 접수번호 (예: '14543호')
    registration_cause: str = ""                    # 등기원인 (예: '매매', '매매예약', '상속')
    registration_cause_date: Optional[str] = None   # 등기원인일자
    owners: List[OwnerInfo] = field(default_factory=list)
    # owners: 소유권 관련 권리자 목록. role 필드로 구체적 역할 구분.
    # 등기명의인표시변경/경정 같이 권리자가 없는 항목은 빈 배열
    creditor: Optional[CreditorInfo] = None         # 채권자 정보 (가압류·경매 등)
    claim_amount: Optional[int] = None              # 청구금액 (원, 가압류 등)
    # --- 말소 관련 ---
    is_cancelled: bool = False                      # 말소 여부. True면 붉은 취소선이 그어진 무효 항목
    cancelled_by_rank: Optional[str] = None         # [수동] 이 항목을 말소시킨 순위번호 (예: '4' → 4번이 본 항목을 말소)
    cancellation_date: Optional[str] = None         # 말소일자
    cancellation_cause: Optional[str] = None        # 말소원인 (예: '해제', '취소')
    cancels_rank: Optional[str] = None              # [능동] 이 항목이 말소하는 대상 순위번호 (말소등기인 경우)
    raw_text: str = ""                              # 원본 셀 텍스트 (파싱 디버깅용)
    remarks: Optional[str] = None                   # 기타사항 (법조문·표시변경 내용 등 권리자가 없는 항목의 상세)


@dataclass
class SectionBEntry:
    """을구 항목 — 소유권 이외의 권리에 관한 사항"""
    rank_number: str            # 순위번호
    registration_type: str      # 등기목적 (예: '근저당권설정', '전세권설정', '지상권설정')
    receipt_date: str = ""      # 접수일자
    receipt_number: str = ""    # 접수번호
    registration_cause: str = ""                    # 등기원인
    registration_cause_date: Optional[str] = None   # 등기원인일자
    # --- 근저당권 ---
    max_claim_amount: Optional[int] = None          # 채권최고액 (원)
    debtor: Optional[OwnerInfo] = None              # 채무자
    mortgagee: Optional[CreditorInfo] = None        # 근저당권자
    # --- 임차권 / 전세권 ---
    deposit_amount: Optional[int] = None            # 보증금 (원)
    monthly_rent: Optional[int] = None              # 차임/월세 (원)
    lease_term: Optional[LeaseTermInfo] = None      # 임대차 기간 정보
    lessee: Optional[LesseeInfo] = None             # 임차인
    lease_area: Optional[str] = None                # 임차 면적
    # --- 지상권 ---
    purpose: Optional[str] = None                   # 지상권 목적
    scope: Optional[str] = None                     # 지상권 범위
    duration: Optional[str] = None                  # 존속기간
    land_rent: Optional[str] = None                 # 지료
    # --- 질권 ---
    bond_amount: Optional[int] = None               # 채권액 (원)
    # --- 공동담보 ---
    collateral_list: Optional[str] = None           # 공동담보목록 번호 (예: '제2016-194호')
    # --- 말소 관련 ---
    is_cancelled: bool = False                      # 말소 여부
    cancelled_by_rank: Optional[str] = None         # [수동] 이 항목을 말소시킨 순위번호
    cancellation_date: Optional[str] = None         # 말소일자
    cancellation_cause: Optional[str] = None        # 말소원인
    cancels_rank: Optional[str] = None              # [능동] 이 항목이 말소하는 대상 순위번호
    raw_text: str = ""                              # 원본 셀 텍스트
    remarks: Optional[str] = None                   # 기타사항


@dataclass
class TitleInfo:
    """표제부 정보"""
    unique_number: str = ""         # 고유번호 (예: '1101-2006-000001')
    property_type: str = "building" # 부동산 유형: 'land' | 'building' | 'aggregate_building'
    address: str = ""               # 소재지 주소 (지번주소)
    road_address: Optional[str] = None     # 도로명주소
    building_name: Optional[str] = None    # 건물명 (집합건물)
    structure: Optional[str] = None        # 구조 (예: '철근콘크리트조')
    roof_type: Optional[str] = None        # 지붕 종류
    floors: int = 0                        # 층수
    building_type: Optional[str] = None    # 건물 용도 (예: '아파트', '단독주택')
    areas: List[FloorArea] = field(default_factory=list)    # 층별 면적 목록
    land_right_ratio: Optional[str] = None         # 대지권 비율
    land_right_area: Optional[float] = None        # 대지권 면적 (㎡)
    exclusive_area: Optional[float] = None         # 전용면적 (㎡)
    total_floor_area: float = 0.0                  # 연면적 (㎡)
    land_type: Optional[str] = None                # 지목 (토지)
    land_area: Optional[str] = None                # 토지 면적
    land_entries: List[LandTitleEntry] = field(default_factory=list)
    building_entries: List[BuildingTitleEntry] = field(default_factory=list)
    exclusive_part_entries: List[ExclusivePartEntry] = field(default_factory=list)
    land_right_entries: List[LandRightEntry] = field(default_factory=list)
    land_right_ratio_entries: List[LandRightRatioEntry] = field(default_factory=list)


@dataclass
class TradeListItem:
    """매매목록 항목"""
    serial_number: str = ""        # 일련번호
    property_description: str = "" # 부동산의 표시
    rank_number: str = ""          # 순위번호
    registration_cause: str = ""   # 등기원인
    correction_cause: str = ""     # 경정원인


@dataclass
class TradeList:
    """매매목록"""
    list_number: str = ""                              # 목록번호 (예: '2016-553')
    trade_amount: Optional[int] = None                 # 거래가액 (원)
    items: List[TradeListItem] = field(default_factory=list)


@dataclass
class MajorSummaryOwnerEntry:
    """주요 등기사항 요약 - 등기명의인 요약"""
    name: str                                           # 등기명의인 성명
    resident_number: Optional[str] = None              # 주민/법인등록번호
    final_share: Optional[str] = None                  # 최종 지분
    address: Optional[str] = None                      # 주소
    rank_number: str = ""                                  # 순위번호


@dataclass
class MajorSummaryRightEntry:
    """주요 등기사항 요약 - 권리사항 요약"""
    rank_number: str            # 순위번호
    registration_purpose: str   # 등기목적
    receipt_date: str = ""      # 접수일자
    receipt_number: str = ""    # 접수번호
    target_owner: Optional[str] = None     # 대상 소유자
    # 요약 텍스트에서 구조화 파싱
    creditor: Optional[str] = None         # 권리자 (근저당권자, 채권자, 지상권자, 전세권자 등)
    max_claim_amount: Optional[int] = None # 채권최고액 (원)
    bond_amount: Optional[int] = None      # 채권액 (원)
    deposit_amount: Optional[int] = None   # 보증금/전세금 (원)
    purpose: Optional[str] = None          # 목적 (지상권 등)
    is_cancelled: bool = False             # 말소 여부 (취소선)


@dataclass
class MajorSummary:
    """주요 등기사항 요약 (참고용)"""
    property_type: str = ""        # 부동산 유형 ('토지', '건물', '집합건물')
    address: str = ""              # 소재지 (예: '경상북도 문경시 농암면 내서리 733 전 714㎡')
    unique_number: str = ""        # 고유번호 (예: '1754-1996-194512')
    owners: List[MajorSummaryOwnerEntry] = field(default_factory=list)
    rights: List[MajorSummaryRightEntry] = field(default_factory=list)


@dataclass
class RegistryData:
    """등기부등본 전체 데이터"""
    unique_number: str
    property_type: str
    property_address: str
    title_info: TitleInfo
    section_a: List[SectionAEntry] = field(default_factory=list)
    section_b: List[SectionBEntry] = field(default_factory=list)
    trade_lists: List[TradeList] = field(default_factory=list)  # 매매목록
    major_summary: Optional[MajorSummary] = None
    viewed_at: Optional[str] = None    # 열람일시 (예: '2025년 04월 01일 13시 06분 16초')
    issued_at: Optional[str] = None    # 발행일시
    verification_image: Optional[str] = None  # 검증 바코드 (data:image/png;base64,...)
    raw_text: str = ""
    # 파싱 품질/디버깅용 메타
    parse_warnings: List[str] = field(default_factory=list)
    parse_stats: Dict[str, Any] = field(default_factory=dict)
    parse_date: str = field(default_factory=lambda: datetime.now().isoformat())


# ==================== 행 단위 워터마크 처리 ====================

def _strip_watermark_fragments_in_row(cells: List[str]) -> List[str]:
    """행 단위로 '열람용' 워터마크가 셀/줄 단위로 쪼개져 들어온 경우 정리한다.

    영향 최소화를 위해, 같은 행에서 '열/람/용' 토큰이 2개 이상 감지될 때만 제거한다.
    """
    tokens = {"열", "람", "용"}
    flat = " ".join((c or "").replace("\n", " ") for c in cells)
    found = [t for t in tokens if re.search(rf"\b{t}\b", flat)]
    if len(found) < 2:
        return cells

    cleaned: List[str] = []
    for c in cells:
        if not c:
            cleaned.append(c)
            continue
        s = c
        # 줄 단위로 들어간 '열/람/용' 제거
        s = re.sub(r"(?m)^\s*(열|람|용)\s*$", "", s)
        s = re.sub(r"\n\s*(열|람|용)\s*$", "", s)
        s = re.sub(r"^\s*(열|람|용)\s*\n", "", s)
        s = re.sub(r"\n{3,}", "\n\n", s).strip()
        cleaned.append(s)
    return cleaned


# ==================== 테이블 행 위치 추출 ====================

def _get_table_row_y_positions(page, table_index: int = 0) -> List[float]:
    """테이블의 각 행의 y좌표(top) 리스트 반환"""
    try:
        tables = page.find_tables()
        if table_index < len(tables):
            table = tables[table_index]
            rows = table.rows
            return [row.bbox[1] for row in rows]  # bbox[1] = top
    except Exception:
        pass
    return []


# ==================== 메인 파싱 클래스 ====================

class RegistryPDFParser:
    """등기부등본 PDF 파서 v1.0.1"""

    # pdfplumber 테이블 추출 설정 (등기부등본 형식 최적화)
    TABLE_SETTINGS = {
        "vertical_strategy": "lines",
        "horizontal_strategy": "lines",
        "snap_tolerance": 5,
        "join_tolerance": 10,
        "intersection_x_tolerance": 5,
        "intersection_y_tolerance": 5,
        "snap_x_tolerance": 5,
        "snap_y_tolerance": 5,
        "min_words_vertical": 3,
        "min_words_horizontal": 1,
        "text_x_tolerance": 3,
        "text_y_tolerance": 3,
        "text_tolerance": 3,
        "edge_min_length": 1,
        "text_align": "left",
    }

    # 섹션 감지 패턴
    # - 일부 PDF는 표 제목(예: '표제부')가 표 밖에 있거나, '표제부' 문구 없이 '토지의 표시'만 있는 경우가 있어
    #   '표제부'를 optional로 처리한다.
    # - '대지권의 목적인 토지의 표시'는 '토지의 표시'를 포함하므로, land_right_land를 title_land보다 먼저 둔다.
    SECTION_PATTERNS = {
        # 집합건물 대지권 관련이 먼저
        'land_right_land': re.compile(r'대지권의\s*목적인\s*토지의\s*표시'),
        'land_right_ratio': re.compile(r'대지권의\s*표시'),

        # 표제부(토지/건물/전유)
        'title_exclusive': re.compile(r'(?:표\s*제\s*부.*)?전유부분의\s*건물의\s*표시'),
        'title_building_1dong': re.compile(r'(?:표\s*제\s*부.*)?1동의\s*건물의\s*표시'),
        'title_land': re.compile(r'(?:표\s*제\s*부.*)?토지의\s*표시'),

        # 갑/을 구
        'section_a': re.compile(r'갑\s*구.*소유권에\s*관한\s*사항'),
        'section_b': re.compile(r'을\s*구.*소유권\s*이외의\s*권리'),

        # 참고용 요약
        'major_summary': re.compile(r'주\s*요\s*등\s*기\s*사\s*항\s*요\s*약'),

        # 부속 목록 (별도 파싱)
        'trade_list': re.compile(r'매\s*매\s*목\s*록'),

        # 파싱 대상 아닌 섹션 → _skip 접두사로 구분
        '_skip_collateral': re.compile(r'공\s*동\s*담\s*보\s*목\s*록'),
        '_skip_sale_list': re.compile(r'매\s*각\s*물\s*건\s*목\s*록'),
    }

    # 페이지 헤더/푸터 패턴
    HEADER_RE = re.compile(
        r'^\[(?:토지|건물|집합건물)\]\s*.+$|'
        r'^표시번호\s+접\s*수|'
        r'^순위번호\s+등\s*기\s*목\s*적'
    )
    FOOTER_RE = re.compile(
        r'열람일시\s*:|'
        r'발행일시\s*:|'
        r'^\d+/\d+$'
    )

    def __init__(self, pdf_buffer: bytes):
        self.pdf_buffer = pdf_buffer
        self.raw_text = ""
        self.cancellation_detector = CancellationDetector()

    def parse(self) -> RegistryData:
        """PDF 파싱 실행"""
        with pdfplumber.open(io.BytesIO(self.pdf_buffer)) as pdf:
            # 1. 전체 페이지 분석
            page_texts = []
            all_tables_by_section: Dict[str, List[Dict]] = {}
            current_section = None

            for pi, page in enumerate(pdf.pages):
                # 말소 감지용 분석 (원본 페이지 — 빨간 선/문자 필요)
                self.cancellation_detector.analyze_page(page, pi)

                # 워터마크 제거된 페이지
                clean_page = filter_watermark(page)

                # 텍스트 추출
                text = clean_page.extract_text() or ""
                page_texts.append(text)

                # 테이블 추출 + 섹션 분류
                table_objs = []
                try:
                    table_objs = clean_page.find_tables(table_settings=self.TABLE_SETTINGS) or []
                except Exception as e:
                    logger.warning("페이지 {} 테이블 추출 실패: {}", pi + 1, e)
                    table_objs = []

                if table_objs:
                    for t_obj in table_objs:
                        table = t_obj.extract()
                        if not table:
                            continue

                        header_text = " ".join(str(c or "") for c in table[0])
                        detected = self._detect_section(header_text)

                        # 컬럼 기반 휴리스틱 (특히 '주요 등기사항 요약' 테이블 등)
                        detected2 = self._classify_table_by_columns(table[0], header_text, detected or current_section)
                        if detected2:
                            detected = detected2

                        # 테이블 상단 컨텍스트(표 제목) 기반 섹션 감지
                        if not detected:
                            detected = self._detect_section_near_table(clean_page, getattr(t_obj, "bbox", None))

                        if detected:
                            if detected == "__skip__":
                                current_section = None
                                continue
                            current_section = detected

                        if not current_section:
                            continue

                        all_tables_by_section.setdefault(current_section, [])

                        # 테이블 행에 페이지/말소 정보 추가
                        for ri, row in enumerate(table):
                            try:
                                row_bbox = t_obj.rows[ri].bbox
                                row_y = row_bbox[1]      # top
                                row_y_bot = row_bbox[3]  # bottom
                            except Exception:
                                row_y = 0.0
                                row_y_bot = 0.0

                            cells = [clean_cell(c) for c in row]
                            cells = _strip_watermark_fragments_in_row(cells)
                            is_cancelled = self.cancellation_detector.is_row_cancelled_range(pi, row_y, row_y_bot)

                            all_tables_by_section[current_section].append({
                                "cells": cells,
                                "page": pi,
                                "row_y": row_y,
                                "is_cancelled": is_cancelled,
                            })
                else:
                    # find_tables가 실패하는 일부 PDF에 대한 fallback
                    tables = clean_page.extract_tables(table_settings=self.TABLE_SETTINGS)
                    for table in tables:
                        if not table:
                            continue

                        header_text = " ".join(str(c or "") for c in table[0])
                        detected = self._detect_section(header_text)
                        detected2 = self._classify_table_by_columns(table[0], header_text, detected or current_section)
                        if detected2:
                            detected = detected2

                        if detected:
                            if detected == "__skip__":
                                current_section = None
                                continue
                            current_section = detected

                        if not current_section:
                            continue

                        all_tables_by_section.setdefault(current_section, [])
                        for ri, row in enumerate(table):
                            cells = [clean_cell(c) for c in row]
                            cells = _strip_watermark_fragments_in_row(cells)
                            all_tables_by_section[current_section].append({
                                "cells": cells,
                                "page": pi,
                                "row_y": 0.0,
                                "is_cancelled": False,
                            })

            self.raw_text = '\n'.join(page_texts)

            # 2. 기본 정보 추출
            unique_number = self._extract_unique_number()
            property_type = self._detect_property_type()
            property_address = self._extract_address()
            viewed_at, issued_at = self._extract_timestamps()
            verification_image = self._extract_verification_image()

            # 2-1. 섹션 기반 property_type 보정 (상단 표기가 생략되거나, 첫 페이지 텍스트 추출이 약한 PDF 대비)
            if all_tables_by_section.get('title_land'):
                property_type = 'land'
            if any(all_tables_by_section.get(k) for k in ('title_exclusive', 'land_right_land', 'land_right_ratio')):
                property_type = 'aggregate_building'

            # 3. 섹션별 파싱
            title_info = self._parse_title(all_tables_by_section, property_type)
            title_info.unique_number = unique_number
            title_info.property_type = property_type
            title_info.address = property_address

            section_a = self._parse_section_a_from_tables(
                all_tables_by_section.get('section_a', [])
            )

            # section_b에 매매목록이 혼입된 경우 분리 (같은 테이블로 감지된 경우 대비)
            section_b_rows = all_tables_by_section.get('section_b', [])
            trade_from_b: List[Dict] = []
            filtered_b_rows: List[Dict] = []
            in_trade = False
            for row in section_b_rows:
                cells = row.get('cells', [])
                text_compact = ''.join(str(c or '') for c in cells).replace(' ', '')
                if '매매목록' in text_compact:
                    in_trade = True
                if in_trade:
                    trade_from_b.append(row)
                else:
                    filtered_b_rows.append(row)

            section_b = self._parse_section_b_from_tables(filtered_b_rows)

            # 매매목록 파싱 (별도 섹션 + section_b에서 분리된 행 합산)
            trade_rows = all_tables_by_section.get('trade_list', []) + trade_from_b
            trade_lists = self._parse_trade_list_from_tables(trade_rows)

            owner_rows = all_tables_by_section.get('major_summary_owners', [])
            right_rows = all_tables_by_section.get('major_summary_rights', [])

            # '주요 등기사항 요약' 테이블이 컬럼 분류에 실패한 경우 → major_summary로 모인 rows를 분해 시도
            if (not owner_rows and not right_rows) and all_tables_by_section.get('major_summary'):
                owner_rows, right_rows = self._infer_major_summary_tables(all_tables_by_section.get('major_summary', []))

            major_summary = self._parse_major_summary_from_tables(owner_rows, right_rows)

            # 4. 텍스트 기반 말소 보강 + 관계 매핑
            self._apply_text_cancellations(section_a)
            self._apply_text_cancellations(section_b)
            self._map_cancellations(section_a)
            self._map_cancellations(section_b)

            # 5. 파싱 품질 메타
            parse_warnings: List[str] = []
            if len(self.raw_text.strip()) < 200:
                parse_warnings.append('TEXT_TOO_SHORT_POSSIBLE_SCANNED_PDF')

            # 표제부 누락 경고
            if property_type == 'land' and not all_tables_by_section.get('title_land'):
                parse_warnings.append('MISSING_TITLE_LAND_TABLE')
            if property_type == 'building' and not all_tables_by_section.get('title_building_1dong'):
                parse_warnings.append('MISSING_TITLE_BUILDING_TABLE')
            if property_type == 'aggregate_building':
                if not all_tables_by_section.get('title_building_1dong'):
                    parse_warnings.append('MISSING_TITLE_BUILDING_TABLE')
                if not all_tables_by_section.get('title_exclusive'):
                    parse_warnings.append('MISSING_TITLE_EXCLUSIVE_TABLE')
                if not all_tables_by_section.get('land_right_ratio'):
                    parse_warnings.append('MISSING_LAND_RIGHT_RATIO_TABLE')

            if not section_a:
                parse_warnings.append('MISSING_SECTION_A')

            expected_summary = bool(self.SECTION_PATTERNS['major_summary'].search(clean_text(self.raw_text)))
            if expected_summary and not (major_summary.owners or major_summary.rights):
                parse_warnings.append('MISSING_MAJOR_SUMMARY')

            parse_stats = {
                'pages': len(pdf.pages),
                'text_len': len(self.raw_text),
                'sections_found': sorted(all_tables_by_section.keys()),
                'rows_by_section': {k: len(v) for k, v in all_tables_by_section.items()},
            }

            return RegistryData(
                unique_number=unique_number,
                property_type=property_type,
                property_address=property_address,
                title_info=title_info,
                section_a=section_a,
                section_b=section_b,
                trade_lists=trade_lists,
                major_summary=major_summary if (major_summary.owners or major_summary.rights) else None,
                viewed_at=viewed_at,
                issued_at=issued_at,
                verification_image=verification_image,
                raw_text=self.raw_text,
                parse_warnings=parse_warnings,
                parse_stats=parse_stats,
            )

    # ==================== 기본 정보 ====================

    def _extract_unique_number(self) -> str:
        # 일부 PDF는 숫자가 공백/줄바꿈으로 분절되어 들어오므로 공백 허용 후 정규화
        match = re.search(r'고유번호\s*[:：]?\s*([\d\s-]{10,})', self.raw_text)
        if not match:
            return ""
        return re.sub(r"\s+", "", match[1])

    def _detect_property_type(self) -> str:
        first_page = self.raw_text[:1000]
        # 명시적 표기
        if '- 토지 -' in first_page or '[토지]' in first_page:
            return 'land'
        if '- 집합건물 -' in first_page or '[집합건물]' in first_page:
            return 'aggregate_building'
        if '- 건물 -' in first_page or '[건물]' in first_page:
            return 'building'

        # 표제부 키워드 기반 (일부 양식은 상단 표기가 생략됨)
        if re.search(r'토지의\s*표시', first_page):
            return 'land'
        if re.search(r'전유부분의\s*건물의\s*표시|대지권의\s*표시', first_page):
            return 'aggregate_building'
        if re.search(r'1동의\s*건물의\s*표시', first_page):
            return 'building'

        # 기본값
        return 'building'

    def _extract_address(self) -> str:
        pattern = r'\[(?:토지|건물|집합건물)\]\s*([^\n]+)'
        match = re.search(pattern, self.raw_text)
        if match:
            addr = match[1].strip()
            addr = WATERMARK_RE.sub('', addr).strip()
            return addr
        return ""

    def _extract_timestamps(self) -> Tuple[Optional[str], Optional[str]]:
        """열람일시 / 발행일시 추출 (정규화된 형식)"""
        viewed_at = None
        issued_at = None
        m = re.search(r'열람일시\s*[:：]\s*(.+?)(?:\n|$)', self.raw_text)
        if m:
            viewed_at = self._normalize_timestamp(clean_text(m[1]))
        m = re.search(r'(?:발행일시|출력일시)\s*[:：]\s*(.+?)(?:\n|$)', self.raw_text)
        if m:
            issued_at = self._normalize_timestamp(clean_text(m[1]))
        return viewed_at, issued_at

    @staticmethod
    def _normalize_timestamp(text: str) -> str:
        """날짜+시간 문자열을 'YYYY년 MM월 DD일 HH시 MM분 SS초' 형식으로 정규화.

        입력 예시:
        - '2025년04월01일 13시06분16초'
        - '2025년 4월 1일 오후 1시6분16초'
        """
        date_match = re.search(r'(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일', text)
        time_match = re.search(r'(오전|오후)?\s*(\d{1,2})시\s*(\d{1,2})분\s*(\d{1,2})초', text)
        if not date_match or not time_match:
            return text

        year = date_match[1]
        month = date_match[2].zfill(2)
        day = date_match[3].zfill(2)

        hour = int(time_match[2])
        ampm = time_match[1]
        if ampm == '오후' and hour < 12:
            hour += 12
        elif ampm == '오전' and hour == 12:
            hour = 0

        minute = time_match[3].zfill(2)
        second = time_match[4].zfill(2)
        return f"{year}년 {month}월 {day}일 {hour:02d}시 {minute}분 {second}초"

    def _extract_verification_image(self) -> Optional[str]:
        """첫 페이지 고유번호 하단 바코드 이미지를 data URI(PNG)로 추출.

        PyMuPDF(fitz)로 첫 페이지의 이미지 객체를 직접 추출한다.
        pdfplumber의 page.images는 벡터/특수 임베딩 이미지를 놓칠 수 있으므로
        fitz.Page.get_images()를 사용한다.
        """
        try:
            import fitz
        except ImportError:
            return None

        try:
            doc = fitz.open(stream=self.pdf_buffer, filetype="pdf")
            page = doc[0]

            # 페이지 내 모든 이미지 참조
            image_list = page.get_images(full=True)
            if not image_list:
                doc.close()
                return None

            # 고유번호 하단 바코드: 일반적으로 첫 페이지 우측 상단의 가장 큰 이미지
            best_img = None
            best_area = 0
            for img_info in image_list:
                xref = img_info[0]
                # 이미지 위치 확인 (페이지 내 bbox)
                rects = page.get_image_rects(xref)
                for rect in rects:
                    # 우측 영역 (페이지 폭의 50% 이후) + 상단 영역 (30% 이내)
                    if rect.x0 > page.rect.width * 0.5 and rect.y0 < page.rect.height * 0.3:
                        area = rect.width * rect.height
                        if area > best_area:
                            best_area = area
                            best_img = xref

            if best_img is None:
                doc.close()
                return None

            # 이미지 데이터 추출 → PNG
            pix = fitz.Pixmap(doc, best_img)
            if pix.n > 4:  # CMYK → RGB
                pix = fitz.Pixmap(fitz.csRGB, pix)
            png_data = pix.tobytes("png")
            doc.close()

            b64 = base64.b64encode(png_data).decode()
            return f"data:image/png;base64,{b64}"

        except Exception as e:
            logger.warning("바코드 이미지 추출 실패: {}", e)
            return None

    # ==================== 섹션 감지 ====================

    def _detect_section(self, text: str) -> Optional[str]:
        text_clean = clean_text(text)
        for key, pattern in self.SECTION_PATTERNS.items():
            if pattern.search(text_clean):
                # _skip 접두사: 공동담보목록 등 → 현재 섹션 리셋 (None 반환)
                if key.startswith('_skip'):
                    return '__skip__'
                return key
        return None

    def _classify_table_by_columns(
        self,
        header_row: List[Any],
        header_text: str,
        current_section: Optional[str],
    ) -> Optional[str]:
        """테이블의 첫 행(컬럼 헤더)을 기반으로 섹션을 판별한다.

        일부 페이지(특히 '주요 등기사항 요약')는 표 제목이 테이블에 포함되지 않아,
        컬럼명으로 섹션을 식별해야 한다.
        """
        cols = " ".join(clean_text(str(c or "")) for c in header_row)
        cols = re.sub(r"\s+", " ", cols).strip()
        cols_compact = cols.replace(" ", "")

        # 주요 등기사항 요약 - 등기명의인 테이블
        # '등기명의인'이 줄바꿈으로 분절되면 '등 기 명 의 인' 형태가 되므로 compact로 매칭
        if "등기명의인" in cols_compact and (
            "최종지분" in cols_compact or "지분" in cols_compact or "순위번호" in cols_compact
        ):
            return "major_summary_owners"

        # 주요 등기사항 요약 - 권리사항 테이블
        if ("주요등기사항" in cols_compact or "등기목적" in cols_compact) and (
            "대상소유자" in cols_compact or "대상소유" in cols_compact
        ):
            return "major_summary_rights"

        # 컨텍스트가 '주요 등기사항 요약'으로 판별된 상태에서 이어지는 표
        if current_section == "major_summary" and ("등기목적" in cols_compact) and ("접수" in cols_compact):
            return "major_summary_rights"

        # 표제부 테이블(표 제목이 표 밖에 있거나, 표 제목이 아예 없는 경우) → 컬럼으로 판별
        if "표시번호" in cols_compact and "지목" in cols_compact and "면적" in cols_compact:
            return "title_land"
        if "표시번호" in cols_compact and "건물내역" in cols_compact:
            return "title_building_1dong"
        if "표시번호" in cols_compact and ("전유" in cols_compact or "전유부분" in cols_compact) and "건물내역" in cols_compact:
            return "title_exclusive"

        return None

    def _infer_major_summary_tables(self, rows: List[Dict]) -> Tuple[List[Dict], List[Dict]]:
        """'주요 등기사항 요약' 섹션에서 owners/rights 표 분리에 실패했을 때 보정."""
        owners: List[Dict] = []
        rights: List[Dict] = []
        mode: Optional[str] = None

        for row in rows:
            cells = row.get('cells') or []
            line = clean_text(" ".join(cells))
            compact = line.replace(" ", "")

            if "등기명의인" in compact and ("최종지분" in compact or "지분" in compact or "순위번호" in compact):
                mode = 'owners'
                owners.append(row)
                continue

            if "순위번호" in compact and ("등기목적" in compact or "주요등기사항" in compact):
                mode = 'rights'
                rights.append(row)
                continue

            if mode == 'owners':
                owners.append(row)
            elif mode == 'rights':
                rights.append(row)

        # 헤더 분리가 실패한 경우: row 내 텍스트 특징으로 약한 분류
        if not owners and not rights:
            for row in rows:
                cells = row.get('cells') or []
                compact = clean_text(" ".join(cells)).replace(" ", "")
                if "등기명의인" in compact:
                    owners.append(row)
                elif "등기목적" in compact or "주요등기사항" in compact:
                    rights.append(row)

        return owners, rights

    def _detect_section_near_table(self, page, bbox: Optional[tuple]) -> Optional[str]:
        """테이블 상단의 텍스트를 이용해 섹션을 판별한다 (표 제목이 테이블 밖에 있는 경우)."""
        if not bbox:
            return None
        try:
            x0, top, x1, bottom = bbox
        except Exception:
            return None

        y0 = max(0, top - 150)
        y1 = min(page.height, top + 15)
        try:
            region = page.within_bbox((0, y0, page.width, y1))
            context_text = region.extract_text() or ""
        except Exception:
            return None

        if not context_text.strip():
            return None
        return self._detect_section(context_text)

    # ==================== 표제부 파싱 ====================

    def _parse_title(self, tables_by_section: Dict, property_type: str) -> TitleInfo:
        info = TitleInfo()

        if property_type == 'land':
            self._parse_title_land(info, tables_by_section.get('title_land', []))
        elif property_type == 'aggregate_building':
            self._parse_title_building(info, tables_by_section.get('title_building_1dong', []))
            self._parse_title_exclusive(info, tables_by_section.get('title_exclusive', []))
            self._parse_land_right_land(info, tables_by_section.get('land_right_land', []))
            self._parse_land_right_ratio(info, tables_by_section.get('land_right_ratio', []))
        else:
            self._parse_title_building(info, tables_by_section.get('title_building_1dong', []))

        # 도로명주소 — 실제 주소 패턴만 매칭 (시/도/군/구 포함)
        road_match = re.search(
            r'\[도로명주소\]\s*\n?\s*'
            r'((?:서울|부산|대구|인천|광주|대전|울산|세종|경기|강원|충북|충남|전북|전남|경북|경남|제주)'
            r'[^\n\[]{5,})',
            self.raw_text
        )
        if road_match:
            info.road_address = clean_text(road_match[1])

        # 건물종류 (토지는 건물종류 없음)
        if property_type != 'land':
            type_patterns = [
                '제2종근린생활시설', '제1종근린생활시설',
                '아파트', '오피스텔', '다세대주택', '다가구주택', '단독주택',
                '근린생활시설', '상가', '업무시설', '주택',
                '공장', '창고', '연립주택',
            ]
            # 표제부 테이블 텍스트에서만 검색
            title_rows = tables_by_section.get('title_building_1dong', [])
            title_row_text = ' '.join(
                ' '.join(str(c) for c in r['cells']) for r in title_rows
            )
            for tp in type_patterns:
                if tp in title_row_text:
                    info.building_type = tp
                    break

        # 면적 합산
        info.total_floor_area = sum(a.area for a in info.areas if not a.is_excluded)

        return info

    def _parse_title_land(self, info: TitleInfo, rows: List[Dict]):
        """토지 표제부 파싱"""
        data_rows = self._merge_continuation_rows(self._skip_header_rows(rows, '표시번호'))
        for row_data in data_rows:
            cells = row_data['cells']
            if len(cells) < 4:
                continue
            land_type = cells[3] if len(cells) > 3 else ""
            area = cells[4] if len(cells) > 4 else ""

            # 축약된 컬럼 수(예: 4칸)에서 면적/지목 위치가 달라지는 케이스 보정
            if (not area) and ('㎡' in land_type):
                area, land_type = land_type, ""
            if not area:
                for c in cells:
                    if '㎡' in (c or ''):
                        area = c
                        break

            entry = LandTitleEntry(
                display_number=cells[0] if len(cells) > 0 else "",
                receipt_date=cells[1] if len(cells) > 1 else "",
                location=cells[2] if len(cells) > 2 else "",
                land_type=land_type,
                area=area,
                cause_and_other=cells[5] if len(cells) > 5 else "",
                is_cancelled=row_data.get('is_cancelled', False),
            )
            info.land_entries.append(entry)

            # 지목, 면적 추출 (최신 항목으로 갱신)
            cleaned_type = clean_text(land_type)
            if cleaned_type:
                info.land_type = cleaned_type
            area_match = re.search(r'([\d,.]+)\s*㎡', area or '')
            if area_match:
                info.land_area = area_match[1] + '㎡'

    def _parse_title_building(self, info: TitleInfo, rows: List[Dict]):
        """건물 표제부 파싱 (1동의 건물의 표시)"""
        data_rows = self._merge_continuation_rows(self._skip_header_rows(rows, '표시번호'))
        full_detail = ""
        for row_data in data_rows:
            cells = row_data['cells']
            if len(cells) < 4:
                continue
            # 셀이 비어있으면 이전 행의 연속
            detail = cells[3] if len(cells) > 3 else ""
            if detail:
                full_detail += "\n" + detail

            entry = BuildingTitleEntry(
                display_number=cells[0] if len(cells) > 0 else "",
                receipt_date=cells[1] if len(cells) > 1 else "",
                location_or_number=cells[2] if len(cells) > 2 else "",
                building_detail=detail,
                cause_and_other=cells[4] if len(cells) > 4 else "",
                is_cancelled=row_data.get('is_cancelled', False),
            )
            info.building_entries.append(entry)

            # 건물명
            if cells[2] and not info.building_name:
                name_match = re.search(r'(\S+(?:아파트|타워|빌|맨션|주택|빌라|오피스텔|빌딩))',
                                       cells[2])
                if name_match:
                    info.building_name = name_match[1]

        # 구조, 지붕, 층수, 면적 추출 (상세 텍스트에서)
        self._extract_building_details(info, full_detail)

    def _parse_title_exclusive(self, info: TitleInfo, rows: List[Dict]):
        """집합건물 전유부분 파싱"""
        data_rows = self._merge_continuation_rows(self._skip_header_rows(rows, '표시번호'))
        for row_data in data_rows:
            cells = row_data['cells']
            if len(cells) < 4:
                continue
            entry = ExclusivePartEntry(
                display_number=cells[0],
                receipt_date=cells[1],
                building_number=cells[2],
                building_detail=cells[3],
                cause_and_other=cells[4] if len(cells) > 4 else "",
                is_cancelled=row_data.get('is_cancelled', False),
            )
            info.exclusive_part_entries.append(entry)

            # 전유면적
            area_match = re.search(r'([\d,.]+)\s*㎡', cells[3] or '')
            if area_match:
                info.exclusive_area = float(area_match[1].replace(',', ''))

    def _parse_land_right_land(self, info: TitleInfo, rows: List[Dict]):
        """대지권의 목적인 토지의 표시"""
        data_rows = self._merge_continuation_rows(self._skip_header_rows(rows, '표시번호'))
        for row_data in data_rows:
            cells = row_data['cells']
            if len(cells) < 4:
                continue
            entry = LandRightEntry(
                display_number=cells[0],
                location=cells[1] if len(cells) > 1 else "",
                land_type=cells[2] if len(cells) > 2 else "",
                area=cells[3] if len(cells) > 3 else "",
                cause_and_other=cells[4] if len(cells) > 4 else "",
            )
            info.land_right_entries.append(entry)

    def _parse_land_right_ratio(self, info: TitleInfo, rows: List[Dict]):
        """대지권의 표시"""
        data_rows = self._merge_continuation_rows(self._skip_header_rows(rows, '표시번호'))
        for row_data in data_rows:
            cells = row_data['cells']
            if len(cells) < 3:
                continue
            entry = LandRightRatioEntry(
                display_number=cells[0],
                land_right_type=cells[1] if len(cells) > 1 else "",
                land_right_ratio=cells[2] if len(cells) > 2 else "",
                cause_and_other=cells[3] if len(cells) > 3 else "",
                is_cancelled=row_data.get('is_cancelled', False),
            )
            info.land_right_ratio_entries.append(entry)

            # 대지권 비율
            ratio_match = re.search(r'(\d+)분의\s*([\d.]+)', cells[2] or '')
            if ratio_match and not info.land_right_ratio:
                info.land_right_ratio = f"{ratio_match[1]}분의 {ratio_match[2]}"

    def _extract_building_details(self, info: TitleInfo, detail_text: str):
        """건물 상세정보 추출 (구조, 지붕, 층수, 면적)"""
        text = clean_text(detail_text)

        # 구조
        structure_match = re.search(
            r'(철근콘크리트구조|철골철근콘크리트구조|목구조|벽돌구조|'
            r'블록구조|경량철골구조|철골구조|조적구조|강구조)',
            text
        )
        if structure_match:
            info.structure = structure_match[1]

        # 지붕
        roof_match = re.search(
            r'((?:철근)?콘크리트\s*지붕|슬래브\s*지붕|기와\s*지붕|'
            r'스라브\s*지붕|평슬래브\s*지붕|\(철근\)콘크리트지붕)',
            text
        )
        if roof_match:
            info.roof_type = roof_match[1]

        # 층수
        floors_match = re.search(r'(\d+)\s*층\s*(?:아파트|오피스텔|근린|주택|상가|업무|건물)', text)
        if not floors_match:
            floors_match = re.search(r'지붕\s*(\d+)\s*층', text)
        if floors_match:
            info.floors = int(floors_match[1])

        # 층별 면적
        area_patterns = [
            r'(지하?\d+층)\s*([\d,.]+)\s*㎡',
            r'(\d+층)\s*([\d,.]+)\s*㎡',
            r'(옥탑\d?층?)\s*([\d,.]+)\s*㎡',
        ]
        seen_floors = set()
        for pat in area_patterns:
            for m in re.finditer(pat, detail_text):
                floor_name = m[1]
                area_val = float(m[2].replace(',', ''))
                if floor_name not in seen_floors:
                    seen_floors.add(floor_name)
                    excluded = '연면적제외' in detail_text[
                        max(0, m.start() - 50):m.end() + 50
                    ]
                    info.areas.append(FloorArea(
                        floor=floor_name, area=area_val, is_excluded=excluded
                    ))

        info.areas.sort(key=lambda x: x.floor)

    # ==================== 갑구/을구 파싱 ====================

    def _parse_section_a_from_tables(self, rows: List[Dict]) -> List[SectionAEntry]:
        """갑구 테이블 파싱"""
        entries = []
        data_rows = self._skip_header_rows(rows, '순위번호')
        merged_rows = self._merge_continuation_rows(data_rows)

        for row_data in merged_rows:
            cells = row_data['cells']
            if len(cells) < 5:
                continue

            rank = clean_text(cells[0])
            if not rank or not re.match(r'\d', rank):
                continue

            # 공동담보목록/매각물건목록/요약 행 필터링
            if '목록번호' in rank or '거래가액' in rank:
                break  # 이후 행은 모두 목록 데이터
            if '등기명의인' in rank:
                break  # 주요 등기사항 요약 섹션
            purpose = clean_text(cells[1])
            if re.match(r'\[(?:토지|건물)\]', purpose):
                continue  # 공동담보목록 항목

            receipt_text = clean_text(cells[2])
            cause_text = clean_text(cells[3])
            detail_text = clean_text(cells[4])
            raw = f"{purpose} {receipt_text} {cause_text} {detail_text}"

            # 등기목적
            reg_type = self._classify_reg_type_a(purpose)

            # 접수 정보
            receipt_date, receipt_number = extract_receipt_info(receipt_text)

            entry = SectionAEntry(
                rank_number=rank.split('\n')[0].strip(),
                registration_type=reg_type,
                receipt_date=receipt_date,
                receipt_number=receipt_number,
                is_cancelled=row_data.get('is_cancelled', False),
                raw_text=raw,
            )

            # 등기원인
            entry.registration_cause = self._extract_cause(cause_text)
            entry.registration_cause_date = parse_date_korean(cause_text)

            # 소유자/채권자/권리자
            self._extract_section_a_details(entry, detail_text, cause_text)

            # 권리자가 없는 항목(등기명의인표시변경/경정 등)은 상세 텍스트를 기타사항으로
            if not entry.owners and not entry.creditor and not entry.remarks and detail_text:
                entry.remarks = detail_text

            # 말소 등기 대상 번호
            cancels_match = re.search(r'(\d+(?:-\d+)?)번', purpose)
            if '말소' in purpose and cancels_match:
                entry.cancels_rank = cancels_match[1]

            entries.append(entry)

        return entries

    def _parse_section_b_from_tables(self, rows: List[Dict]) -> List[SectionBEntry]:
        """을구 테이블 파싱"""
        entries = []
        data_rows = self._skip_header_rows(rows, '순위번호')
        merged_rows = self._merge_continuation_rows(data_rows)

        for row_data in merged_rows:
            cells = row_data['cells']
            if len(cells) < 5:
                continue

            rank = clean_text(cells[0])
            if not rank or not re.match(r'\d', rank):
                continue

            # 공동담보목록/매각물건목록/요약 행 필터링
            if '목록번호' in rank or '거래가액' in rank:
                break  # 이후 행은 모두 목록 데이터
            if '등기명의인' in rank:
                break  # 주요 등기사항 요약 섹션
            purpose = clean_text(cells[1])
            if re.match(r'\[(?:토지|건물)\]', purpose):
                continue  # 공동담보목록 항목

            receipt_text = clean_text(cells[2])
            cause_text = clean_text(cells[3])
            detail_text = clean_text(cells[4])
            raw = f"{purpose} {receipt_text} {cause_text} {detail_text}"

            reg_type = self._classify_reg_type_b(purpose)
            receipt_date, receipt_number = extract_receipt_info(receipt_text)

            entry = SectionBEntry(
                rank_number=rank.split('\n')[0].strip(),
                registration_type=reg_type,
                receipt_date=receipt_date,
                receipt_number=receipt_number,
                is_cancelled=row_data.get('is_cancelled', False),
                raw_text=raw,
            )

            entry.registration_cause = self._extract_cause(cause_text)
            entry.registration_cause_date = parse_date_korean(cause_text)

            # 상세 파싱
            self._extract_section_b_details(entry, detail_text, cause_text)

            # 말소 대상
            cancels_match = re.search(r'(\d+(?:-\d+)?)번', purpose)
            if '말소' in purpose and cancels_match:
                entry.cancels_rank = cancels_match[1]

            entries.append(entry)

        return entries

    def _parse_trade_list_from_tables(self, rows: List[Dict]) -> List[TradeList]:
        """매매목록 테이블 파싱"""
        if not rows:
            return []

        trade = TradeList()
        for row_data in rows:
            cells = row_data.get('cells', [])
            if not cells:
                continue

            line = ' '.join(str(c or '') for c in cells)
            line_clean = clean_text(line)
            compact = line_clean.replace(' ', '')

            # 섹션 헤더 (【 매 매 목 록 】) 건너뛰기
            if '【' in line or '】' in line:
                continue

            # 메타 정보: 목록번호
            if '목록번호' in compact:
                m = re.search(r'(\d[\d-]+)', compact.replace('목록번호', '', 1))
                if m:
                    trade.list_number = m[1]
                continue

            # 메타 정보: 거래가액
            if '거래가액' in compact:
                trade.trade_amount = parse_amount(line_clean)
                continue

            # 컬럼 헤더 건너뛰기
            if '일련번호' in compact or '부동산' in compact:
                continue

            # 빈 행 건너뛰기
            if not line_clean.strip():
                continue

            # 이하여백 건너뛰기
            if '이하여백' in compact:
                continue

            # 데이터 행: 일련번호(숫자)로 시작
            first = clean_text(str(cells[0] or ''))
            if first and re.match(r'\d+$', first):
                item = TradeListItem(serial_number=first)
                if len(cells) > 1:
                    item.property_description = clean_text(str(cells[1] or ''))
                if len(cells) > 2:
                    item.rank_number = clean_text(str(cells[2] or ''))
                if len(cells) > 3:
                    # 예비란: 등기원인 / 경정원인 (같은 셀 또는 별도 셀)
                    cause_text = clean_text(str(cells[3] or ''))
                    item.registration_cause = cause_text
                if len(cells) > 4:
                    item.correction_cause = clean_text(str(cells[4] or ''))
                trade.items.append(item)

        if trade.list_number or trade.items:
            return [trade]
        return []

    # ==================== 등기유형 분류 ====================

    def _classify_reg_type_a(self, text: str) -> str:
        # 등기목적은 법률 복합어 — PDF 줄바꿈으로 생긴 공백 제거
        text = clean_text(text).replace(' ', '')
        # 말소 패턴 우선
        if '말소' in text:
            m = re.search(r'(\d+(?:-\d+)?번?\S*말소)', text)
            return m[1] if m else text
        # 구체적인 타입을 앞에 (부분문자열 오인식 방지: 소유권이전청구권가등기 > 소유권이전)
        types = [
            '소유권이전청구권가등기', '소유권보존', '소유권이전',
            '가처분', '가압류', '압류',
            '임의경매개시결정', '강제경매개시결정', '경매개시결정',
            '등기명의인표시변경', '등기명의인표시경정',
        ]
        for t in types:
            if t in text:
                return t
        return text[:40] if len(text) > 40 else text

    def _classify_reg_type_b(self, text: str) -> str:
        # 등기목적은 법률 복합어 — PDF 줄바꿈으로 생긴 공백 제거
        text = clean_text(text).replace(' ', '')
        if '말소' in text:
            m = re.search(r'(\d+(?:-\d+)?번?\S*말소)', text)
            return m[1] if m else text
        types = [
            '근저당권설정', '근저당권이전', '근저당권변경',
            '근저당권부채권질권설정',
            '근질권설정', '저당권설정',
            '전세권설정', '전세권이전',
            '주택임차권', '임차권설정',
            '지상권설정', '지상권이전',
            '가등기', '등기명의인표시변경',
        ]
        for t in types:
            if t in text:
                return t
        return text[:40] if len(text) > 40 else text

    def _extract_cause(self, text: str) -> str:
        """등기원인 추출"""
        text = clean_text(text)
        # 구체적인 원인을 앞에 (부분문자열 오인식 방지: 매매예약>매매, 압류해제>해제 등)
        causes = [
            '매매예약', '매매', '상속', '증여', '신탁', '경락', '판결', '교환',
            '협의분할', '법원경매', '공매', '설정계약',
            '확정채권양도', '확정채무의면책적인수', '면책적인수', '취급지점변경',
            '압류해제', '압류', '해지', '해제', '취하', '취소결정',
            '전거', '행정구역변경', '도로명주소변경', '명칭변경', '주소변경',
        ]
        for c in causes:
            if c in text.replace(' ', ''):
                return c
        # 법원 결정 패턴 (공백 제거 후 매칭 — PDF 줄바꿈 분절 대응, 사건번호 포함)
        compact = text.replace(' ', '')
        # 선행 날짜를 제거하여 \w+가 날짜까지 탐욕적으로 매칭하는 것을 방지
        compact_no_date = re.sub(r'\d{4}년\d{1,2}월\d{1,2}일', '', compact)
        court_match = re.search(
            r'(\w+법원\w*의\w+(?:\([^)]*\))?)',
            compact_no_date
        )
        if court_match:
            return court_match[1]
        return text[:30] if text else ""

    # ==================== 갑구 상세 ====================

    def _extract_section_a_details(self, entry: SectionAEntry,
                                   detail: str, cause: str):
        full = detail + " " + cause

        # 공유자/지분 패턴 (복수 공유자)
        for m in re.finditer(
            r'지분\s+\d+분의\s+\d+\s+(\S+)\s+([\d]{6}-[\d*]{7}|[\d]{6}-[\d]{7})',
            full
        ):
            name = m[1]
            rn = m[2]
            addr, rem = self._extract_address_after(full, m.end())
            share = self._extract_share_near(full, m.start())
            entry.owners.append(OwnerInfo(
                name=name, resident_number=rn, address=addr, share=share, role='공유자'
            ))
            if rem and not entry.remarks:
                entry.remarks = rem

        # 소유자 (단독 소유자 — 지분 없는 경우)
        if not entry.owners:
            for m in re.finditer(
                r'소유자\s+(\S+)\s+([\d]{6}-[\d*]{7}|[\d]{6}-[\d]{7})',
                full
            ):
                name = m[1]
                rn = m[2]
                addr, rem = self._extract_address_after(full, m.end())
                share = self._extract_share_near(full, m.start())
                entry.owners.append(OwnerInfo(
                    name=name, resident_number=rn, address=addr, share=share, role='소유자'
                ))
                if rem and not entry.remarks:
                    entry.remarks = rem

        # 소유자 (주민번호 없는 패턴 — 법인 등)
        if not entry.owners:
            owner_match = re.search(r'소유자\s+(\S+)', full)
            if owner_match:
                name = owner_match[1]
                rn = parse_resident_number(full)
                addr, rem = self._extract_address_after(full, owner_match.end())
                share = self._extract_share_near(full, owner_match.start())
                entry.owners.append(OwnerInfo(
                    name=name, resident_number=rn, address=addr, share=share, role='소유자'
                ))
                if rem and not entry.remarks:
                    entry.remarks = rem

        # 수탁자
        if not entry.owners:
            trustee_match = re.search(r'수탁자\s+(\S+)', full)
            if trustee_match:
                name = trustee_match[1]
                rn = parse_resident_number(full)
                entry.owners.append(OwnerInfo(
                    name=name, resident_number=rn, role='수탁자'
                ))

        # 가등기권자 (지분 정보가 이름 앞에 올 수 있음)
        if not entry.owners:
            provisional = re.search(
                r'가등기권자\s+(?:지분\s+\d+분의\s+\d+\s+)?(\S+)', full
            )
            if provisional:
                name = provisional[1]
                rn = parse_resident_number(full[provisional.start():])
                addr, rem = self._extract_address_after(full, provisional.end())
                entry.owners.append(OwnerInfo(
                    name=name, resident_number=rn, address=addr, role='가등기권자'
                ))
                if rem and not entry.remarks:
                    entry.remarks = rem

        # 채권자
        creditor_match = re.search(r'채권자\s+(\S+)', full)
        if creditor_match:
            rn = parse_resident_number(
                full[creditor_match.start():]
            )
            addr, _ = self._extract_address_after(full, creditor_match.end())
            entry.creditor = CreditorInfo(
                name=creditor_match[1], resident_number=rn, address=addr
            )

        # 권리자
        if not entry.creditor:
            rights_match = re.search(r'권리자\s+(\S+)', full)
            if rights_match:
                rn = parse_resident_number(full[rights_match.start():])
                addr, _ = self._extract_address_after(full, rights_match.end())
                entry.creditor = CreditorInfo(
                    name=rights_match[1], resident_number=rn, address=addr
                )
                # 처분청 등 추가 정보를 remarks로
                extra = re.search(r'처분청\s+(.+)', full[rights_match.end():])
                if extra and not entry.remarks:
                    entry.remarks = f"처분청 {clean_text(extra[1])}"

        # 청구금액
        entry.claim_amount = parse_amount(full)

        # 거래가액
        if not entry.claim_amount:
            trade_match = re.search(r'거래가액\s*금\s*([\d,]+)\s*원', full)
            if trade_match:
                entry.claim_amount = int(trade_match[1].replace(',', ''))

        # 피보전권리
        right_match = re.search(r'피보전권리\s+(.+?)(?:채권자|금지|$)', full)
        if right_match and not entry.registration_cause:
            entry.registration_cause = clean_text(right_match[1])

    # ==================== 을구 상세 ====================

    def _extract_section_b_details(self, entry: SectionBEntry,
                                   detail: str, cause: str):
        full = detail + " " + cause

        # 채권최고액
        entry.max_claim_amount = parse_amount(
            re.search(r'채권최고액\s*금\s*([\d,]+)\s*원', full)[0]
        ) if re.search(r'채권최고액\s*금\s*([\d,]+)\s*원', full) else None

        # 채권액 (질권 등)
        if not entry.max_claim_amount:
            bond = re.search(r'채권액\s*금\s*([\d,]+)\s*원', full)
            if bond:
                entry.bond_amount = int(bond[1].replace(',', ''))

        # 채무자
        debtor_match = re.search(r'채무자\s+(\S+)', full)
        if debtor_match:
            # 다음 역할 키워드까지만 탐색 (근저당권자 등의 주민번호 오인식 방지)
            debtor_segment = re.split(
                r'근저당권자|저당권자|채권자|권리자|전세권자|임차권자|지상권자',
                full[debtor_match.start():]
            )[0]
            rn = parse_resident_number(debtor_segment)
            addr, _ = self._extract_address_after(full, debtor_match.end())
            entry.debtor = OwnerInfo(
                name=debtor_match[1], resident_number=rn, address=addr
            )

        # 근저당권자
        mortgagee_match = re.search(r'근저당권자\s+(\S+)', full)
        if mortgagee_match:
            rn = parse_resident_number(full[mortgagee_match.start():])
            addr, _ = self._extract_address_after(full, mortgagee_match.end())
            entry.mortgagee = CreditorInfo(
                name=mortgagee_match[1], resident_number=rn, address=addr
            )

        # 채권자 (질권 등)
        if not entry.mortgagee:
            creditor_match = re.search(r'채권자\s+(\S+)', full)
            if creditor_match:
                rn = parse_resident_number(full[creditor_match.start():])
                addr, _ = self._extract_address_after(full, creditor_match.end())
                entry.mortgagee = CreditorInfo(
                    name=creditor_match[1], resident_number=rn, address=addr
                )

        # 임차보증금
        deposit = re.search(r'임차보증금\s*금\s*([\d,]+)\s*원', full)
        if deposit:
            entry.deposit_amount = int(deposit[1].replace(',', ''))

        # 전세금
        jeonse = re.search(r'전세금\s*금\s*([\d,]+)\s*원', full)
        if jeonse and not entry.deposit_amount:
            entry.deposit_amount = int(jeonse[1].replace(',', ''))

        # 차임(월세)
        rent = re.search(r'차\s*임\s*금?\s*([\d,]+)\s*원', full)
        if rent:
            entry.monthly_rent = int(rent[1].replace(',', ''))

        # 임차권자
        lessee_match = re.search(r'임차권자\s+(\S+)', full)
        if lessee_match:
            rn = parse_resident_number(full[lessee_match.start():])
            entry.lessee = LesseeInfo(
                name=lessee_match[1], resident_number=rn
            )

        # 임대차 기간
        if '임대차계약일자' in full or '확정일자' in full:
            lt = LeaseTermInfo()
            contract = re.search(r'임대차계약일자\s*(\d{4}년\s*\d+월\s*\d+일)', full)
            if contract:
                lt.contract_date = contract[1]
            fixed = re.search(r'확정일자\s*(\d{4}년\s*\d+월\s*\d+일)', full)
            if fixed:
                lt.fixed_date = fixed[1]
            entry.lease_term = lt

        # 지상권 정보
        purpose_match = re.search(r'목\s*적\s+(.+?)(?:범\s*위|존속|지\s*료|$)', full)
        if purpose_match:
            entry.purpose = clean_text(purpose_match[1])
        scope_match = re.search(r'범\s*위\s+(.+?)(?:존속|지\s*료|지상권자|$)', full)
        if scope_match:
            entry.scope = clean_text(scope_match[1])
        duration_match = re.search(r'존속기간\s+(.+?)(?:지\s*료|지상권자|$)', full)
        if duration_match:
            entry.duration = clean_text(duration_match[1])
        rent_match = re.search(r'지\s*료\s+(\S+)', full)
        if rent_match:
            entry.land_rent = rent_match[1]

        # 지상권자
        if not entry.mortgagee:
            surface_match = re.search(r'지상권자\s+(\S+)', full)
            if surface_match:
                rn = parse_resident_number(full[surface_match.start():])
                addr, _ = self._extract_address_after(full, surface_match.end())
                entry.mortgagee = CreditorInfo(
                    name=surface_match[1], resident_number=rn, address=addr
                )

        # 공동담보목록
        collateral = re.search(r'공동담보목록\s+(\S+)', full)
        if collateral:
            entry.collateral_list = collateral[1]

    # ==================== 헬퍼 ====================

    @staticmethod
    def _extract_address_after(text: str, pos: int) -> Tuple[Optional[str], Optional[str]]:
        """특정 위치 이후의 주소 및 기타사항 추출. Returns (address, remarks)."""
        remaining = text[pos:pos + 200]
        remarks: Optional[str] = None
        # 주소 종료 기준: 법조문, 참조번호, 날짜, 역할 키워드
        stop = re.search(
            r'(?:부동산|민법|상법|형법|세법|등기)\S*법\b|제\d+조|규정에\s*의하여|전산이기|'
            r'매매목록|공동담보목록|\d{4}년\s*\d{1,2}월\s*\d{1,2}일|'
            r'근저당권자|저당권자|채권자|채무자|소유자|공유자|권리자|'
            r'임차권자|전세권자|지상권자|가등기권자|수탁자|처분청',
            remaining
        )
        if stop:
            remarks_raw = clean_text(remaining[stop.start():])
            remarks = remarks_raw if remarks_raw else None
            remaining = remaining[:stop.start()].rstrip()
        # 주소 패턴: 시/도로 시작
        addr_match = re.search(
            r'((?:서울|부산|대구|인천|광주|대전|울산|세종|경기|강원|충청|전라|경상|제주)'
            r'(?:특별시|광역시|특별자치시|도|특별자치도)?'
            r'\S*(?:\s+\S+){1,8})',
            remaining
        )
        if addr_match:
            return clean_text(addr_match[1]), remarks
        # 군/구 시작 패턴
        addr_match2 = re.search(r'(\S+[군구시읍면동리]\s+\S+(?:\s+\S+){0,6})', remaining)
        if addr_match2:
            return clean_text(addr_match2[1]), remarks
        return None, remarks

    @staticmethod
    def _extract_share_near(text: str, pos: int) -> Optional[str]:
        """지분 정보 추출"""
        nearby = text[max(0, pos - 100):pos + 200]
        share_match = re.search(r'(\d+)분의\s*(\d+)', nearby)
        if share_match:
            return f"{share_match[1]}분의 {share_match[2]}"
        if '단독소유' in nearby:
            return '단독소유'
        return None

    @staticmethod
    def _skip_header_rows(rows: List[Dict], keyword: str) -> List[Dict]:
        """헤더 행(섹션 타이틀, 컬럼 헤더) 건너뛰기"""
        result = []
        for row_data in rows:
            cells = row_data['cells']
            first_cell = ' '.join(str(c) for c in cells[:2] if c)
            first_cell_clean = clean_text(first_cell)
            # 섹션 제목 행 (【 】 포함)
            if '【' in first_cell or '】' in first_cell:
                continue
            # 컬럼 헤더 행
            if keyword in first_cell_clean:
                continue
            # 빈 행
            if all(not c for c in cells):
                continue
            result.append(row_data)
        return result

    @staticmethod
    def _merge_continuation_rows(rows: List[Dict]) -> List[Dict]:
        """연속 행 병합 (순위번호가 비어있으면 이전 행에 합침)"""
        merged = []
        for row_data in rows:
            cells = row_data['cells']
            rank = clean_text(cells[0]) if cells else ""

            # 다른 섹션의 컬럼 헤더/타이틀이 섞여 들어오는 경우 병합으로 데이터가 오염되는 것을 방지
            if rank and not re.match(r"\d", rank):
                if any(k in rank for k in (
                    "등기명의인", "순위번호", "주요등기사항", "대상소유자",
                    "공동담보", "매각", "매매", "목록번호", "거래가액",
                )):
                    continue

            # 순위번호가 있으면 새 항목
            if rank and re.match(r'\d', rank):
                merged.append(row_data)
            elif merged:
                # 이전 행에 텍스트 병합
                prev = merged[-1]
                for i in range(len(cells)):
                    if i < len(prev['cells']) and cells[i]:
                        if prev['cells'][i]:
                            prev['cells'][i] += '\n' + cells[i]
                        else:
                            prev['cells'][i] = cells[i]
                # 말소 상태 전파
                if row_data.get('is_cancelled'):
                    prev['is_cancelled'] = True

        return merged

    # ==================== 말소 처리 ====================

    def _apply_text_cancellations(self, entries: List):
        """텍스트 기반 말소 보강 (붉은 선 감지 못한 경우 대비)"""
        for entry in entries:
            raw = entry.raw_text or ""
            reg_type = entry.registration_type or ""

            # "X번~말소" 등기는 그 자체가 말소 등기
            if '말소' in reg_type:
                cancels_match = re.search(r'(\d+(?:-\d+)?)번', reg_type)
                if cancels_match and not entry.cancels_rank:
                    entry.cancels_rank = cancels_match[1]

            # 등기원인이 해지/해제/취하/취소 → 말소 처리
            cause = entry.registration_cause or ""
            if cause in ('해지', '해제', '취하', '취소결정', '압류해제'):
                if not entry.cancels_rank:
                    cancels_match = re.search(r'(\d+(?:-\d+)?)번', reg_type)
                    if cancels_match:
                        entry.cancels_rank = cancels_match[1]

    def _map_cancellations(self, entries: List):
        """말소 관계 매핑: 말소등기 → 원본등기"""
        cancel_map: Dict[str, Dict] = {}

        for entry in entries:
            if entry.cancels_rank:
                cancel_map[entry.cancels_rank] = {
                    'rank_number': entry.rank_number,
                    'date': entry.receipt_date,
                    'cause': entry.registration_cause or entry.cancellation_cause,
                }

        for entry in entries:
            if entry.rank_number in cancel_map:
                info = cancel_map[entry.rank_number]
                entry.is_cancelled = True
                entry.cancelled_by_rank = info['rank_number']
                entry.cancellation_date = info['date']
                entry.cancellation_cause = info['cause']

    # ==================== 주요 등기사항 요약 ====================

    def _parse_major_summary_from_tables(
        self,
        owner_rows: List[Dict[str, Any]],
        right_rows: List[Dict[str, Any]],
    ) -> MajorSummary:
        """'주요 등기사항 요약 (참고용)' 섹션 파싱."""
        owners = self._parse_major_summary_owners(owner_rows)
        rights = self._parse_major_summary_rights(right_rows)
        summary = MajorSummary(owners=owners, rights=rights)

        # 요약 페이지 상단 헤더에서 기본 정보 추출
        summary_start = self.raw_text.find('주요')
        if summary_start >= 0:
            header = self.raw_text[summary_start:summary_start + 500]
            # 고유번호
            un_match = re.search(r'고유번호\s*[:：]?\s*([\d\s-]+)', header)
            if un_match:
                summary.unique_number = re.sub(r'\s+', '', un_match[1]).strip()
            # [토지/건물/집합건물] 소재지
            pt_match = re.search(r'\[(토지|건물|집합건물)\]\s*(.+?)(?:\n|$)', header)
            if pt_match:
                summary.property_type = pt_match[1]
                summary.address = clean_text(pt_match[2])

        return summary

    def _parse_major_summary_owners(self, tables: List[Dict[str, Any]]) -> List[MajorSummaryOwnerEntry]:
        """주요 등기사항 요약 - 등기명의인 테이블 파싱"""
        data_rows = self._skip_header_rows(tables, keyword="등기명의인")
        owners: List[MajorSummaryOwnerEntry] = []

        for row in data_rows:
            cells = row.get("cells", [])
            if len(cells) < 5:
                continue
            name = clean_text(cells[0])
            if not name:
                continue
            resident = clean_text(cells[1])
            share = clean_text(cells[2])
            addr = clean_text(cells[3])
            ranks_raw = clean_text(cells[4])

            owners.append(MajorSummaryOwnerEntry(
                name=name,
                resident_number=resident or None,
                final_share=share or None,
                address=addr or None,
                rank_number=ranks_raw,
            ))

        return owners

    def _parse_major_summary_rights(self, tables: List[Dict[str, Any]]) -> List[MajorSummaryRightEntry]:
        """주요 등기사항 요약 - 권리사항 테이블 파싱"""
        data_rows = self._skip_header_rows(tables, keyword="순위번호")
        merged_rows = self._merge_continuation_rows(data_rows)

        rights: List[MajorSummaryRightEntry] = []
        for row in merged_rows:
            cells = row.get("cells", [])
            if len(cells) < 5:
                continue
            rank = clean_text(cells[0])
            purpose = clean_text(cells[1])
            receipt_info = clean_text(cells[2])
            summary_text = clean_text(cells[3])
            target_owner = clean_text(cells[4])

            if not rank or not re.match(r"\d", rank):
                continue

            receipt_date, receipt_number = extract_receipt_info(receipt_info)

            entry = MajorSummaryRightEntry(
                rank_number=rank,
                registration_purpose=purpose,
                receipt_date=receipt_date,
                receipt_number=receipt_number,
                target_owner=target_owner or None,
                is_cancelled=row.get('is_cancelled', False),
            )

            # 요약 텍스트에서 구조화 파싱
            self._parse_summary_right_detail(entry, summary_text)

            rights.append(entry)

        return rights

    @staticmethod
    def _parse_summary_right_detail(entry: MajorSummaryRightEntry, text: str):
        """요약 텍스트에서 구조화된 필드를 추출한다."""
        # 채권최고액
        m = re.search(r'채권최고액\s*(금\s*[\d,]+\s*원)', text)
        if m:
            entry.max_claim_amount = parse_amount(m[1])

        # 채권액
        m = re.search(r'채권액\s*(금\s*[\d,]+\s*원)', text)
        if m:
            entry.bond_amount = parse_amount(m[1])

        # 보증금/전세금
        m = re.search(r'(?:보증금|전세금)\s*(금\s*[\d,]+\s*원)', text)
        if m:
            entry.deposit_amount = parse_amount(m[1])

        # 목적 (지상권 등) — "목 적" 뒤 ~ 권리자 키워드 전까지
        m = re.search(r'목\s*적\s+(.+?)(?:지상권자|전세권자|임차권자|채권자|근저당권자|$)', text)
        if m:
            entry.purpose = clean_text(m[1])

        # 권리자 (근저당권자, 채권자, 지상권자, 전세권자 등)
        m = re.search(
            r'(?:근저당권자|저당권자|채권자|지상권자|전세권자|임차권자|권리자)\s+(\S+)',
            text
        )
        if m:
            entry.creditor = m[1]


# ==================== 외부 인터페이스 ====================

PARSER_VERSION = "1.0.1"


def parse_registry_pdf(pdf_buffer: bytes) -> Dict[str, Any]:
    """PDF 파싱 실행 (외부 인터페이스)"""
    logger.info("등기부등본 파싱 시작 (v{}, {}KB)", PARSER_VERSION, len(pdf_buffer) // 1024)
    parser = RegistryPDFParser(pdf_buffer)
    data = parser.parse()

    result = to_dict(data)

    # 통계 추가
    result['section_a_count'] = len(result.get('section_a', []))
    result['section_b_count'] = len(result.get('section_b', []))
    result['active_section_a_count'] = sum(
        1 for e in result.get('section_a', []) if not e.get('is_cancelled')
    )
    result['active_section_b_count'] = sum(
        1 for e in result.get('section_b', []) if not e.get('is_cancelled')
    )

    logger.info(
        "파싱 완료 | {} | 갑구 {}건(유효 {}) 을구 {}건(유효 {})",
        result.get('property_address', '?'),
        result['section_a_count'], result['active_section_a_count'],
        result['section_b_count'], result['active_section_b_count'],
    )

    return result


# ==================== BaseParser 플러그인 래퍼 ====================

class RegistryParserV1_0_1(BaseParser):
    """등기부등본 파서 v1.0.1 — BaseParser 플러그인 인터페이스"""

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
        return PARSER_VERSION

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
            ('[토지]', 0.05), ('[건물]', 0.05), ('[집합건물]', 0.05),
        ]
        for keyword, weight in indicators:
            if keyword in text_sample:
                score += weight
        return min(score, 1.0)

    def parse(self, pdf_buffer: bytes) -> ParseResult:
        """PDF 파싱 → ParseResult 반환"""
        result_dict = parse_registry_pdf(pdf_buffer)

        return ParseResult(
            document_type="registry",
            document_sub_type=result_dict.get("property_type", ""),
            parser_version=self.parser_version(),
            data=result_dict,
            raw_text=result_dict.get("raw_text", ""),
            errors=result_dict.get("parse_warnings", []),
            confidence=1.0,
            metadata=result_dict.get("parse_stats", {}),
        )

    def mask_for_demo(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """등기부등본 전용 데모 마스킹"""
        masked = copy.deepcopy(data)

        # 표제부 면적은 첫 층만
        if 'title_info' in masked and 'areas' in masked['title_info']:
            masked['title_info']['areas'] = masked['title_info']['areas'][:1]

        # 갑구 첫 항목만, 개인정보 마스킹
        if 'section_a' in masked and masked['section_a']:
            first_entry = masked['section_a'][0]
            if first_entry.get('owner'):
                owner = first_entry['owner']
                if owner.get('name'):
                    name = owner['name']
                    owner['name'] = (
                        name[0] + '*' * (len(name) - 2) + name[-1]
                        if len(name) > 2 else name[0] + '*'
                    )
                owner['resident_number'] = '******-*******'
                owner['address'] = '***' if owner.get('address') else None
            masked['section_a'] = [first_entry]

        # 을구 첫 항목만, 금액 숨김
        if 'section_b' in masked and masked['section_b']:
            first_entry = masked['section_b'][0]
            first_entry['max_claim_amount'] = None
            first_entry['deposit_amount'] = None
            first_entry['mortgagee'] = None
            first_entry['lessee'] = None
            masked['section_b'] = [first_entry]

        # 주요 등기사항 요약(참고용) 마스킹
        if masked.get('major_summary'):
            ms = masked['major_summary']
            owners = ms.get('owners') or []
            if owners:
                for o in owners[:1]:
                    if o.get('resident_number'):
                        o['resident_number'] = '******'
                    if o.get('address'):
                        o['address'] = (o['address'][:5] + '...') if len(o['address']) > 5 else o['address']
                    if o.get('name'):
                        o['name'] = o['name'][0] + '*'
                ms['owners'] = owners[:1]

            rights = ms.get('rights') or []
            if rights:
                ms['rights'] = rights[:1]

        return masked
