"""
등기부등본 PDF 파싱 엔진 v2
- pdfplumber 테이블 기반 추출 (텍스트 + 구조 동시 파싱)
- 붉은 선/글자 기반 말소사항 감지
- 페이지 간 테이블 연결
- 토지 / 건물 / 집합건물 지원
"""
import re
import io
import json
from typing import List, Optional, Dict, Any, Tuple, Set
from datetime import datetime
from dataclasses import dataclass, field, asdict
from loguru import logger
import pdfplumber


# ==================== 데이터 클래스 ====================

@dataclass
class FloorArea:
    floor: str
    area: float
    is_excluded: bool = False


@dataclass
class OwnerInfo:
    name: str
    resident_number: Optional[str] = None
    address: Optional[str] = None
    share: Optional[str] = None


@dataclass
class CreditorInfo:
    name: str
    resident_number: Optional[str] = None
    address: Optional[str] = None


@dataclass
class LesseeInfo:
    name: str
    resident_number: Optional[str] = None
    address: Optional[str] = None


@dataclass
class LeaseTermInfo:
    contract_date: Optional[str] = None
    resident_registration_date: Optional[str] = None
    possession_start_date: Optional[str] = None
    fixed_date: Optional[str] = None


@dataclass
class LandTitleEntry:
    """표제부 — 토지의 표시 항목"""
    display_number: str = ""
    receipt_date: str = ""
    location: str = ""
    land_type: str = ""
    area: str = ""
    cause_and_other: str = ""
    is_cancelled: bool = False


@dataclass
class BuildingTitleEntry:
    """표제부 — 건물의 표시 항목 (1동 / 전유부분)"""
    display_number: str = ""
    receipt_date: str = ""
    location_or_number: str = ""
    building_detail: str = ""
    cause_and_other: str = ""
    is_cancelled: bool = False


@dataclass
class LandRightEntry:
    """대지권의 목적인 토지의 표시"""
    display_number: str = ""
    location: str = ""
    land_type: str = ""
    area: str = ""
    cause_and_other: str = ""


@dataclass
class ExclusivePartEntry:
    """전유부분의 건물의 표시"""
    display_number: str = ""
    receipt_date: str = ""
    building_number: str = ""
    building_detail: str = ""
    cause_and_other: str = ""
    is_cancelled: bool = False


@dataclass
class LandRightRatioEntry:
    """대지권의 표시"""
    display_number: str = ""
    land_right_type: str = ""
    land_right_ratio: str = ""
    cause_and_other: str = ""
    is_cancelled: bool = False


@dataclass
class SectionAEntry:
    """갑구 항목"""
    rank_number: str
    registration_type: str
    receipt_date: str = ""
    receipt_number: str = ""
    registration_cause: str = ""
    registration_cause_date: Optional[str] = None
    owners: List[OwnerInfo] = field(default_factory=list)
    creditor: Optional[CreditorInfo] = None
    claim_amount: Optional[int] = None
    # 말소 관련
    is_cancelled: bool = False
    cancellation_rank_number: Optional[str] = None
    cancellation_date: Optional[str] = None
    cancellation_cause: Optional[str] = None
    cancels_rank_number: Optional[str] = None
    raw_text: str = ""

    # 하위호환
    @property
    def owner(self) -> Optional[OwnerInfo]:
        return self.owners[0] if self.owners else None


@dataclass
class SectionBEntry:
    """을구 항목"""
    rank_number: str
    registration_type: str
    receipt_date: str = ""
    receipt_number: str = ""
    registration_cause: str = ""
    registration_cause_date: Optional[str] = None
    # 근저당권
    max_claim_amount: Optional[int] = None
    debtor: Optional[OwnerInfo] = None
    mortgagee: Optional[CreditorInfo] = None
    # 임차권 / 전세권
    deposit_amount: Optional[int] = None
    monthly_rent: Optional[int] = None
    lease_term: Optional[LeaseTermInfo] = None
    lessee: Optional[LesseeInfo] = None
    lease_area: Optional[str] = None
    # 지상권
    purpose: Optional[str] = None
    scope: Optional[str] = None
    duration: Optional[str] = None
    land_rent: Optional[str] = None
    # 질권
    bond_amount: Optional[int] = None
    # 말소 관련
    is_cancelled: bool = False
    cancellation_rank_number: Optional[str] = None
    cancellation_date: Optional[str] = None
    cancellation_cause: Optional[str] = None
    cancels_rank_number: Optional[str] = None
    raw_text: str = ""


@dataclass
class TitleInfo:
    """표제부 정보"""
    unique_number: str = ""
    property_type: str = "building"  # land, building, aggregate_building
    address: str = ""
    road_address: Optional[str] = None
    building_name: Optional[str] = None
    structure: Optional[str] = None
    roof_type: Optional[str] = None
    floors: int = 0
    building_type: Optional[str] = None
    areas: List[FloorArea] = field(default_factory=list)
    land_right_ratio: Optional[str] = None
    exclusive_area: Optional[float] = None
    total_floor_area: float = 0.0
    # 토지
    land_type: Optional[str] = None
    land_area: Optional[str] = None
    # 상세 항목
    land_entries: List[LandTitleEntry] = field(default_factory=list)
    building_entries: List[BuildingTitleEntry] = field(default_factory=list)
    exclusive_part_entries: List[ExclusivePartEntry] = field(default_factory=list)
    land_right_entries: List[LandRightEntry] = field(default_factory=list)
    land_right_ratio_entries: List[LandRightRatioEntry] = field(default_factory=list)


@dataclass
class RegistryData:
    """등기부등본 전체 데이터"""
    unique_number: str
    property_type: str
    property_address: str
    title_info: TitleInfo
    section_a: List[SectionAEntry] = field(default_factory=list)
    section_b: List[SectionBEntry] = field(default_factory=list)
    raw_text: str = ""
    parse_date: str = field(default_factory=lambda: datetime.now().isoformat())
    parser_version: str = ""
    errors: List[str] = field(default_factory=list)


# ==================== 유틸리티 함수 ====================

_WATERMARK_RE = re.compile(r'열\s*람\s*용')


def _is_watermark_char(obj: dict) -> bool:
    """pdfplumber 문자 객체가 워터마크인지 판별 (회색 색상 기반)"""
    if obj.get('object_type') != 'char':
        return False
    color = obj.get('non_stroking_color')
    if isinstance(color, (tuple, list)) and len(color) >= 3:
        return all(0.5 < c < 1.0 for c in color[:3])
    return False


def _filter_watermark(page):
    """페이지에서 워터마크 문자를 제거한 필터링된 페이지 반환"""
    return page.filter(lambda obj: not _is_watermark_char(obj))


def _clean_text(text: Optional[str]) -> str:
    """텍스트 정리 (공백 정규화)"""
    if not text:
        return ""
    text = _WATERMARK_RE.sub('', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def _clean_cell(cell: Optional[str]) -> str:
    """테이블 셀 정리"""
    if not cell:
        return ""
    return cell.strip()


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


# ==================== 붉은 선 감지 ====================

class CancellationDetector:
    """페이지별 붉은 선/글자 기반 말소 감지"""

    def __init__(self):
        # page_index -> set of y-coordinate ranges that are cancelled
        self._cancelled_y_ranges: Dict[int, List[Tuple[float, float]]] = {}
        # page_index -> set of cancelled char y-coords
        self._cancelled_char_ys: Dict[int, Set[float]] = {}

    def analyze_page(self, page, page_index: int):
        """페이지의 붉은 선, 붉은 사각형, 붉은 글자 분석"""
        # 붉은 선 수집
        red_line_ys = set()
        for line in (page.lines or []):
            color = line.get('stroking_color')
            if self._is_red(color):
                y = round(line['top'], 0)
                red_line_ys.add(y)

        # 붉은 사각형(박스형 말소 표시) 수집
        for rect in (page.rects or []):
            color = rect.get('stroking_color') or rect.get('non_stroking_color')
            if self._is_red(color):
                top = round(rect['top'], 0)
                bottom = round(rect['bottom'], 0)
                # 사각형의 전체 높이 범위를 말소 영역으로 등록
                for y in range(int(top), int(bottom) + 1):
                    red_line_ys.add(float(y))

        if red_line_ys:
            ranges = []
            for y in sorted(red_line_ys):
                ranges.append((y - 6, y + 6))  # 선 위아래 6pt 범위
            self._cancelled_y_ranges[page_index] = self._merge_ranges(ranges)

        # 붉은 글자 y좌표 수집
        red_char_ys = set()
        for ch in (page.chars or []):
            sc = ch.get('stroking_color')
            nsc = ch.get('non_stroking_color')
            if self._is_red(sc) or self._is_red(nsc):
                red_char_ys.add(round(ch['top'], 0))
        if red_char_ys:
            self._cancelled_char_ys[page_index] = red_char_ys

    def is_row_cancelled(self, page_index: int, row_y: float) -> bool:
        """해당 페이지의 y좌표가 말소 영역인지 확인"""
        y = round(row_y, 0)

        # 붉은 선 범위 체크
        ranges = self._cancelled_y_ranges.get(page_index, [])
        for y_min, y_max in ranges:
            if y_min <= y <= y_max:
                return True

        # 붉은 글자 y좌표 체크
        char_ys = self._cancelled_char_ys.get(page_index, set())
        for cy in char_ys:
            if abs(cy - y) <= 6:
                return True

        return False

    def is_table_row_cancelled(self, page_index: int, row_cells_y: List[float]) -> bool:
        """테이블 행의 셀들 y좌표로 말소 여부 판단"""
        if not row_cells_y:
            return False
        # 셀 y좌표 중 하나라도 말소 영역에 있으면 말소
        for y in row_cells_y:
            if self.is_row_cancelled(page_index, y):
                return True
        return False

    @staticmethod
    def _is_red(color) -> bool:
        if not color:
            return False
        if isinstance(color, (list, tuple)):
            if len(color) >= 3:
                r, g, b = color[0], color[1], color[2]
                if isinstance(r, (int, float)):
                    # RGB 0-1 스케일
                    if r > 0.7 and g < 0.3 and b < 0.3:
                        return True
                    # RGB 0-255 스케일
                    if r > 180 and g < 80 and b < 80:
                        return True
            elif len(color) == 4:
                c, m, y_val, k = color
                if m > 0.5 and y_val > 0.3 and c < 0.2:
                    return True
        return False

    @staticmethod
    def _merge_ranges(ranges: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
        if not ranges:
            return []
        sorted_ranges = sorted(ranges)
        merged = [sorted_ranges[0]]
        for start, end in sorted_ranges[1:]:
            if start <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], end))
            else:
                merged.append((start, end))
        return merged


# ==================== 메인 파싱 클래스 ====================

class RegistryPDFParser:
    """등기부등본 PDF 파서 v2"""

    # 섹션 감지 패턴
    SECTION_PATTERNS = {
        'title_land': re.compile(r'표\s*제\s*부.*토지의\s*표시'),
        'title_building_1dong': re.compile(r'표\s*제\s*부.*1동의\s*건물의\s*표시'),
        'title_exclusive': re.compile(r'표\s*제\s*부.*전유부분의\s*건물의\s*표시'),
        'land_right_land': re.compile(r'대지권의\s*목적인\s*토지의\s*표시'),
        'land_right_ratio': re.compile(r'대지권의\s*표시'),
        'section_a': re.compile(r'갑\s*구.*소유권에\s*관한\s*사항'),
        'section_b': re.compile(r'을\s*구.*소유권\s*이외의\s*권리'),
        # 파싱 대상 아닌 섹션 → _skip 접두사로 구분
        '_skip_collateral': re.compile(r'공\s*동\s*담\s*보\s*목\s*록'),
        '_skip_sale_list': re.compile(r'매\s*각\s*물\s*건\s*목\s*록'),
        '_skip_summary': re.compile(r'주\s*요\s*등\s*기\s*사\s*항\s*요\s*약'),
        '_skip_ownership_summary': re.compile(r'등\s*기\s*명\s*의\s*인.*등\s*록\s*번\s*호'),
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
        self.normalized_text = ""  # 헤더/푸터 제거된 텍스트 (정규식 추출용)
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
                clean_page = _filter_watermark(page)

                # 텍스트 추출
                text = clean_page.extract_text() or ""
                page_texts.append(text)

                # find_tables()로 테이블 객체를 얻고, 같은 객체에서
                # extract()와 rows(y좌표)를 모두 가져옴 — 단일 소스
                found_tables = clean_page.find_tables()
                for ft in found_tables:
                    table = ft.extract()
                    if not table:
                        continue

                    # 첫 행에서 섹션 감지
                    header_text = ' '.join(str(c or '') for c in table[0])
                    detected = self._detect_section(header_text)
                    if detected:
                        if detected == '__skip__':
                            current_section = None
                            continue
                        current_section = detected

                    if current_section:
                        if current_section not in all_tables_by_section:
                            all_tables_by_section[current_section] = []

                        # 동일 테이블 객체에서 행 y좌표 추출
                        row_ys = [row.bbox[1] for row in ft.rows]
                        for ri, row in enumerate(table):
                            row_y = row_ys[ri] if ri < len(row_ys) else 0.0
                            is_cancelled = self.cancellation_detector.is_row_cancelled(pi, row_y)
                            all_tables_by_section[current_section].append({
                                'cells': [_clean_cell(c) for c in row],
                                'page': pi,
                                'row_y': row_y,
                                'is_cancelled': is_cancelled,
                            })

            self.raw_text = '\n'.join(page_texts)

            # 헤더/푸터 제거한 normalized_text 생성 (정규식 추출용)
            normalized_lines = []
            for line in self.raw_text.split('\n'):
                stripped = line.strip()
                if stripped and not self.HEADER_RE.match(stripped) and not self.FOOTER_RE.search(stripped):
                    normalized_lines.append(line)
            self.normalized_text = '\n'.join(normalized_lines)

            # 2. 기본 정보 추출
            unique_number = self._extract_unique_number()
            property_type = self._detect_property_type()
            property_address = self._extract_address()

            # 3. 섹션별 파싱 (부분 실패 허용)
            errors: List[str] = []

            title_info = TitleInfo()
            try:
                title_info = self._parse_title(all_tables_by_section, property_type)
                title_info.unique_number = unique_number
                title_info.property_type = property_type
                title_info.address = property_address
            except Exception as e:
                errors.append(f"표제부 파싱 실패: {e}")
                logger.warning(f"표제부 파싱 실패: {e}")
                title_info.unique_number = unique_number
                title_info.property_type = property_type
                title_info.address = property_address

            section_a: List[SectionAEntry] = []
            try:
                section_a = self._parse_section_a_from_tables(
                    all_tables_by_section.get('section_a', [])
                )
            except Exception as e:
                errors.append(f"갑구 파싱 실패: {e}")
                logger.warning(f"갑구 파싱 실패: {e}")

            section_b: List[SectionBEntry] = []
            try:
                section_b = self._parse_section_b_from_tables(
                    all_tables_by_section.get('section_b', [])
                )
            except Exception as e:
                errors.append(f"을구 파싱 실패: {e}")
                logger.warning(f"을구 파싱 실패: {e}")

            # 4. 텍스트 기반 말소 보강 + 관계 매핑
            self._apply_text_cancellations(section_a)
            self._apply_text_cancellations(section_b)
            self._map_cancellations(section_a)
            self._map_cancellations(section_b)

            return RegistryData(
                unique_number=unique_number,
                property_type=property_type,
                property_address=property_address,
                title_info=title_info,
                section_a=section_a,
                section_b=section_b,
                raw_text=self.raw_text,
                errors=errors,
            )

    # ==================== 기본 정보 ====================

    def _extract_unique_number(self) -> str:
        match = re.search(r'고유번호\s*([\d-]+)', self.normalized_text)
        return match[1] if match else ""

    def _detect_property_type(self) -> str:
        first_page = self.normalized_text[:500]
        if '- 토지 -' in first_page or '[토지]' in first_page:
            return 'land'
        if '- 집합건물 -' in first_page or '[집합건물]' in first_page:
            return 'aggregate_building'
        return 'building'

    def _extract_address(self) -> str:
        pattern = r'\[(?:토지|건물|집합건물)\]\s*([^\n]+)'
        match = re.search(pattern, self.normalized_text)
        if match:
            addr = match[1].strip()
            addr = _WATERMARK_RE.sub('', addr).strip()
            return addr
        return ""

    # ==================== 섹션 감지 ====================

    def _detect_section(self, text: str) -> Optional[str]:
        text_clean = _clean_text(text)
        for key, pattern in self.SECTION_PATTERNS.items():
            if pattern.search(text_clean):
                # _skip 접두사: 공동담보목록 등 → 현재 섹션 리셋 (None 반환)
                if key.startswith('_skip'):
                    return '__skip__'
                return key
        return None

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
            self.normalized_text
        )
        if road_match:
            info.road_address = _clean_text(road_match[1])

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
        data_rows = self._skip_header_rows(rows, '표시번호')
        for row_data in data_rows:
            cells = row_data['cells']
            if len(cells) < 5:
                continue
            entry = LandTitleEntry(
                display_number=cells[0],
                receipt_date=cells[1],
                location=cells[2],
                land_type=cells[3],
                area=cells[4],
                is_cancelled=row_data.get('is_cancelled', False),
            )
            info.land_entries.append(entry)

            # 지목, 면적 추출 (최신 항목으로 갱신)
            cleaned_type = _clean_text(cells[3])
            if cleaned_type:
                info.land_type = cleaned_type
            area_match = re.search(r'([\d,.]+)\s*㎡', cells[4] or '')
            if area_match:
                info.land_area = area_match[1] + '㎡'

    def _parse_title_building(self, info: TitleInfo, rows: List[Dict]):
        """건물 표제부 파싱 (1동의 건물의 표시)"""
        data_rows = self._skip_header_rows(rows, '표시번호')
        full_detail = ""
        for row_data in data_rows:
            cells = row_data['cells']
            if len(cells) < 5:
                continue
            # 셀이 비어있으면 이전 행의 연속
            detail = cells[3] if len(cells) > 3 else ""
            if detail:
                full_detail += "\n" + detail

            entry = BuildingTitleEntry(
                display_number=cells[0],
                receipt_date=cells[1],
                location_or_number=cells[2],
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
        data_rows = self._skip_header_rows(rows, '표시번호')
        for row_data in data_rows:
            cells = row_data['cells']
            if len(cells) < 5:
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
        data_rows = self._skip_header_rows(rows, '표시번호')
        for row_data in data_rows:
            cells = row_data['cells']
            if len(cells) < 5:
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
        data_rows = self._skip_header_rows(rows, '표시번호')
        for row_data in data_rows:
            cells = row_data['cells']
            if len(cells) < 4:
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
        text = _clean_text(detail_text)

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

            rank = _clean_text(cells[0])
            if not rank or not re.match(r'\d', rank):
                continue

            # 공동담보목록/매각물건목록/요약 행 필터링
            if '목록번호' in rank or '거래가액' in rank:
                break  # 이후 행은 모두 목록 데이터
            if '등기명의인' in rank:
                break  # 주요 등기사항 요약 섹션
            purpose = _clean_text(cells[1])
            if re.match(r'\[(?:토지|건물)\]', purpose):
                continue  # 공동담보목록 항목

            receipt_text = _clean_text(cells[2])
            cause_text = _clean_text(cells[3])
            detail_text = _clean_text(cells[4])
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

            # 말소 등기 대상 번호
            cancels_match = re.search(r'(\d+(?:-\d+)?)번', purpose)
            if '말소' in purpose and cancels_match:
                entry.cancels_rank_number = cancels_match[1]

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

            rank = _clean_text(cells[0])
            if not rank or not re.match(r'\d', rank):
                continue

            # 공동담보목록/매각물건목록/요약 행 필터링
            if '목록번호' in rank or '거래가액' in rank:
                break  # 이후 행은 모두 목록 데이터
            if '등기명의인' in rank:
                break  # 주요 등기사항 요약 섹션
            purpose = _clean_text(cells[1])
            if re.match(r'\[(?:토지|건물)\]', purpose):
                continue  # 공동담보목록 항목

            receipt_text = _clean_text(cells[2])
            cause_text = _clean_text(cells[3])
            detail_text = _clean_text(cells[4])
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
                entry.cancels_rank_number = cancels_match[1]

            entries.append(entry)

        return entries

    # ==================== 등기유형 분류 ====================

    def _classify_reg_type_a(self, text: str) -> str:
        text = _clean_text(text)
        # 말소 패턴 우선
        if '말소' in text:
            m = re.search(r'(\d+(?:-\d+)?번?\S*말소)', text)
            return m[1] if m else text
        types = [
            '소유권보존', '소유권이전', '소유권이전청구권가등기',
            '가처분', '가압류', '압류',
            '임의경매개시결정', '강제경매개시결정', '경매개시결정',
            '등기명의인표시변경', '등기명의인표시경정',
        ]
        for t in types:
            if t in text.replace(' ', ''):
                return t
        return text[:40] if len(text) > 40 else text

    def _classify_reg_type_b(self, text: str) -> str:
        text = _clean_text(text)
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
            if t in text.replace(' ', ''):
                return t
        return text[:40] if len(text) > 40 else text

    def _extract_cause(self, text: str) -> str:
        """등기원인 추출"""
        text = _clean_text(text)
        causes = [
            '매매', '상속', '증여', '신탁', '경락', '판결', '교환',
            '협의분할', '법원경매', '공매', '설정계약', '매매예약',
            '확정채권양도', '면책적인수', '취급지점변경',
            '해지', '해제', '취하', '취소결정', '압류해제',
            '확정채무의면책적인수',
        ]
        for c in causes:
            if c in text.replace(' ', ''):
                return c
        # 법원 결정 패턴
        court_match = re.search(r'((?:\S+법원|지방법원)\S*의\s*\S+)', text)
        if court_match:
            return court_match[1]
        return text[:30] if text else ""

    # ==================== 갑구 상세 ====================

    def _extract_section_a_details(self, entry: SectionAEntry,
                                   detail: str, cause: str):
        full = detail + " " + cause

        # 공유자/지분 패턴 (복수 공유자)
        for m in re.finditer(
            r'지분\s+\d+분의\s+\d+\s+(\S+)\s+([\d]{6}-[\d*○●]{7}|[\d]{6}-[\d]{7})',
            full
        ):
            name = m[1]
            rn = m[2]
            addr = self._extract_address_after(full, m.end())
            share = self._extract_share_near(full, m.start())
            entry.owners.append(OwnerInfo(
                name=name, resident_number=rn, address=addr, share=share
            ))

        # 소유자 (단독 소유자 — 지분 없는 경우)
        if not entry.owners:
            for m in re.finditer(
                r'소유자\s+(\S+)\s+([\d]{6}-[\d*○●]{7}|[\d]{6}-[\d]{7})',
                full
            ):
                name = m[1]
                rn = m[2]
                addr = self._extract_address_after(full, m.end())
                share = self._extract_share_near(full, m.start())
                entry.owners.append(OwnerInfo(
                    name=name, resident_number=rn, address=addr, share=share
                ))

        # 소유자 (주민번호 없는 패턴 — 법인 등)
        if not entry.owners:
            owner_match = re.search(r'소유자\s+(\S+)', full)
            if owner_match:
                name = owner_match[1]
                rn = parse_resident_number(full)
                addr = self._extract_address_after(full, owner_match.end())
                share = self._extract_share_near(full, owner_match.start())
                entry.owners.append(OwnerInfo(
                    name=name, resident_number=rn, address=addr, share=share
                ))

        # 수탁자
        if not entry.owners:
            trustee_match = re.search(r'수탁자\s+(\S+)', full)
            if trustee_match:
                name = trustee_match[1]
                rn = parse_resident_number(full)
                entry.owners.append(OwnerInfo(
                    name=name, resident_number=rn
                ))

        # 가등기권자 (지분 정보가 이름 앞에 올 수 있음)
        if not entry.owners:
            provisional = re.search(
                r'가등기권자\s+(?:지분\s+\d+분의\s+\d+\s+)?(\S+)', full
            )
            if provisional:
                name = provisional[1]
                rn = parse_resident_number(full[provisional.start():])
                entry.owners.append(OwnerInfo(name=name, resident_number=rn))

        # 채권자
        creditor_match = re.search(r'채권자\s+(\S+)', full)
        if creditor_match:
            rn = parse_resident_number(
                full[creditor_match.start():]
            )
            entry.creditor = CreditorInfo(
                name=creditor_match[1], resident_number=rn
            )

        # 권리자
        if not entry.creditor:
            rights_match = re.search(r'권리자\s+(\S+)', full)
            if rights_match:
                rn = parse_resident_number(full[rights_match.start():])
                entry.creditor = CreditorInfo(
                    name=rights_match[1], resident_number=rn
                )

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
            entry.registration_cause = _clean_text(right_match[1])

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
            rn = parse_resident_number(full[debtor_match.start():])
            addr = self._extract_address_after(full, debtor_match.end())
            entry.debtor = OwnerInfo(
                name=debtor_match[1], resident_number=rn, address=addr
            )

        # 근저당권자
        mortgagee_match = re.search(r'근저당권자\s+(\S+)', full)
        if mortgagee_match:
            rn = parse_resident_number(full[mortgagee_match.start():])
            entry.mortgagee = CreditorInfo(
                name=mortgagee_match[1], resident_number=rn
            )

        # 채권자 (질권 등)
        if not entry.mortgagee:
            creditor_match = re.search(r'채권자\s+(\S+)', full)
            if creditor_match:
                rn = parse_resident_number(full[creditor_match.start():])
                entry.mortgagee = CreditorInfo(
                    name=creditor_match[1], resident_number=rn
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
            entry.purpose = _clean_text(purpose_match[1])
        scope_match = re.search(r'범\s*위\s+(.+?)(?:존속|지\s*료|지상권자|$)', full)
        if scope_match:
            entry.scope = _clean_text(scope_match[1])
        duration_match = re.search(r'존속기간\s+(.+?)(?:지\s*료|지상권자|$)', full)
        if duration_match:
            entry.duration = _clean_text(duration_match[1])
        rent_match = re.search(r'지\s*료\s+(\S+)', full)
        if rent_match:
            entry.land_rent = rent_match[1]

        # 공동담보
        collateral = re.search(r'공동담보목록\s+(\S+)', full)
        if collateral:
            if not entry.raw_text:
                entry.raw_text = ""
            entry.raw_text += f" 공동담보: {collateral[1]}"

    # ==================== 헬퍼 ====================

    @staticmethod
    def _extract_address_after(text: str, pos: int) -> Optional[str]:
        """특정 위치 이후의 주소 추출"""
        remaining = text[pos:pos + 200]
        # 주소 패턴: 시/도로 시작
        addr_match = re.search(
            r'((?:서울|부산|대구|인천|광주|대전|울산|세종|경기|강원|충청|전라|경상|제주)'
            r'(?:특별시|광역시|특별자치시|도|특별자치도)?'
            r'\S*(?:\s+\S+){1,8})',
            remaining
        )
        if addr_match:
            return _clean_text(addr_match[1])
        # 군/구 시작 패턴
        addr_match2 = re.search(r'(\S+[군구시읍면동리]\s+\S+(?:\s+\S+){0,6})', remaining)
        if addr_match2:
            return _clean_text(addr_match2[1])
        return None

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
            first_cell_clean = _clean_text(first_cell)
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
            rank = _clean_text(cells[0]) if cells else ""

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
                if cancels_match and not entry.cancels_rank_number:
                    entry.cancels_rank_number = cancels_match[1]

            # 등기원인이 해지/해제/취하/취소 → 말소 처리
            cause = entry.registration_cause or ""
            if cause in ('해지', '해제', '취하', '취소결정', '압류해제'):
                if not entry.cancels_rank_number:
                    cancels_match = re.search(r'(\d+(?:-\d+)?)번', reg_type)
                    if cancels_match:
                        entry.cancels_rank_number = cancels_match[1]

    def _map_cancellations(self, entries: List):
        """말소 관계 매핑: 말소등기 → 원본등기"""
        cancel_map: Dict[str, Dict] = {}

        for entry in entries:
            if entry.cancels_rank_number:
                cancel_map[entry.cancels_rank_number] = {
                    'rank_number': entry.rank_number,
                    'date': entry.receipt_date,
                    'cause': entry.registration_cause or entry.cancellation_cause,
                }

        for entry in entries:
            if entry.rank_number in cancel_map:
                info = cancel_map[entry.rank_number]
                entry.is_cancelled = True
                entry.cancellation_rank_number = info['rank_number']
                entry.cancellation_date = info['date']
                entry.cancellation_cause = info['cause']


# ==================== 외부 인터페이스 ====================

PARSER_VERSION = "2.1.0"


def parse_registry_pdf(pdf_buffer: bytes) -> Dict[str, Any]:
    """PDF 파싱 실행 (외부 인터페이스)"""
    parser = RegistryPDFParser(pdf_buffer)
    data = parser.parse()
    data.parser_version = PARSER_VERSION

    result = _to_dict(data)

    # 하위호환: owner 필드 (첫 번째 소유자)
    for entry in result.get('section_a', []):
        owners = entry.pop('owners', [])
        entry['owner'] = owners[0] if owners else None
        entry['owners'] = owners

    # 통계 추가
    result['section_a_count'] = len(result.get('section_a', []))
    result['section_b_count'] = len(result.get('section_b', []))
    result['active_section_a_count'] = sum(
        1 for e in result.get('section_a', []) if not e.get('is_cancelled')
    )
    result['active_section_b_count'] = sum(
        1 for e in result.get('section_b', []) if not e.get('is_cancelled')
    )

    return result


def _to_dict(obj):
    """데이터클래스를 딕셔너리로 변환"""
    if hasattr(obj, '__dataclass_fields__'):
        d = {}
        for k in obj.__dataclass_fields__:
            val = getattr(obj, k)
            d[k] = _to_dict(val)
        return d
    elif isinstance(obj, list):
        return [_to_dict(item) for item in obj]
    elif isinstance(obj, dict):
        return {k: _to_dict(v) for k, v in obj.items()}
    else:
        return obj


def mask_for_demo(data: Dict[str, Any]) -> Dict[str, Any]:
    """데모 버전용 데이터 마스킹"""
    import copy
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

    return masked
