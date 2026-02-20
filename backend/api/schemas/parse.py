"""PDF 파싱 관련 스키마"""
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field
from api.schemas.common import ResponseBase


class FloorArea(BaseModel):
    floor: str = Field(description="층 정보 (예: '1층', '지하1층')")
    area: float = Field(description="면적 (㎡)")
    is_excluded: bool = Field(default=False, description="제외 면적 여부")


class OwnerInfo(BaseModel):
    name: str = Field(description="성명 또는 법인명")
    resident_number: Optional[str] = Field(default=None, description="주민등록번호 또는 법인등록번호 (마스킹 포함, 예: '650603-*******')")
    address: Optional[str] = Field(default=None, description="주소")
    share: Optional[str] = Field(default=None, description="지분 (공유 시, 예: '3분의 1'). 단독소유는 null")
    role: Optional[str] = Field(default=None, description="등기부상 역할: '소유자' | '공유자' | '가등기권자' | '수탁자'")


class CreditorInfo(BaseModel):
    name: str = Field(description="채권자 성명 또는 법인명")
    resident_number: Optional[str] = Field(default=None, description="주민등록번호 또는 법인등록번호")
    address: Optional[str] = Field(default=None, description="주소")


class LesseeInfo(BaseModel):
    name: str = Field(description="임차인 성명")
    resident_number: Optional[str] = Field(default=None, description="주민등록번호")
    address: Optional[str] = Field(default=None, description="주소")


class LeaseTermInfo(BaseModel):
    contract_date: Optional[str] = Field(default=None, description="계약일자")
    resident_registration_date: Optional[str] = Field(default=None, description="주민등록일자")
    possession_start_date: Optional[str] = Field(default=None, description="점유개시일")
    fixed_date: Optional[str] = Field(default=None, description="확정일자")


class SectionAEntry(BaseModel):
    """갑구 항목 — 소유권에 관한 사항"""
    rank_number: str = Field(description="순위번호 (예: '1', '1-1', '2'). 부기등기는 '-'로 구분")
    registration_type: str = Field(description="등기목적 (예: '소유권이전', '소유권이전청구권가등기', '등기명의인표시변경')")
    receipt_date: str = Field(description="접수일자 (예: '2007년9월11일')")
    receipt_number: str = Field(description="접수번호 (예: '14543호')")
    registration_cause: Optional[str] = Field(default=None, description="등기원인 (예: '매매', '매매예약', '상속')")
    registration_cause_date: Optional[str] = Field(default=None, description="등기원인일자")
    owners: List[OwnerInfo] = Field(
        default=[],
        description="소유자/권리자 목록. 등기목적에 따라 주체가 다름: "
                    "소유권이전→소유자, 소유권이전청구권가등기→가등기권자, 수탁→수탁자. "
                    "공유의 경우 N명. 등기명의인표시변경/경정은 빈 배열"
    )
    creditor: Optional[CreditorInfo] = Field(default=None, description="채권자 정보 (가압류·경매 등 채권 관련 등기 시)")
    claim_amount: Optional[int] = Field(default=None, description="청구금액 (원, 가압류 등)")
    is_cancelled: bool = Field(default=False, description="말소 여부. True면 붉은 취소선이 그어진 무효 항목")
    cancelled_by_rank: Optional[str] = Field(
        default=None,
        description="[수동] 이 항목을 말소시킨 순위번호 (예: '4' → 4번 항목에 의해 말소됨)"
    )
    cancellation_date: Optional[str] = Field(default=None, description="말소일자")
    cancellation_cause: Optional[str] = Field(default=None, description="말소원인 (예: '해제', '취소')")
    cancels_rank: Optional[str] = Field(
        default=None,
        description="[능동] 이 항목이 말소하는 대상 순위번호 (말소등기인 경우)"
    )
    raw_text: Optional[str] = Field(default=None, description="원본 셀 텍스트 (파싱 디버깅용)")
    remarks: Optional[str] = Field(
        default=None,
        description="기타사항. 권리자가 없는 항목(등기명의인표시변경/경정 등)의 상세 내용, "
                    "또는 법조문(부동산등기법 전산이기 등)"
    )


class SectionBEntry(BaseModel):
    """을구 항목 — 소유권 이외의 권리에 관한 사항"""
    rank_number: str = Field(description="순위번호")
    registration_type: str = Field(description="등기목적 (예: '근저당권설정', '전세권설정', '지상권설정')")
    receipt_date: str = Field(description="접수일자")
    receipt_number: str = Field(description="접수번호")
    registration_cause: Optional[str] = Field(default=None, description="등기원인")
    registration_cause_date: Optional[str] = Field(default=None, description="등기원인일자")
    max_claim_amount: Optional[int] = Field(default=None, description="채권최고액 (원, 근저당권)")
    debtor: Optional[OwnerInfo] = Field(default=None, description="채무자 정보 (근저당권 등)")
    mortgagee: Optional[CreditorInfo] = Field(default=None, description="근저당권자 정보")
    deposit_amount: Optional[int] = Field(default=None, description="보증금 (원, 전세권·임차권)")
    monthly_rent: Optional[int] = Field(default=None, description="차임/월세 (원)")
    lease_term: Optional[LeaseTermInfo] = Field(default=None, description="임대차 기간 정보")
    lessee: Optional[LesseeInfo] = Field(default=None, description="임차인 정보")
    lease_area: Optional[str] = Field(default=None, description="임차 면적")
    is_cancelled: bool = Field(default=False, description="말소 여부")
    cancelled_by_rank: Optional[str] = Field(default=None, description="[수동] 이 항목을 말소시킨 순위번호")
    cancellation_date: Optional[str] = Field(default=None, description="말소일자")
    cancellation_cause: Optional[str] = Field(default=None, description="말소원인")
    cancels_rank: Optional[str] = Field(default=None, description="[능동] 이 항목이 말소하는 대상 순위번호")
    raw_text: Optional[str] = Field(default=None, description="원본 셀 텍스트")


class LandTitleEntry(BaseModel):
    """표제부 — 토지의 표시 항목"""
    display_number: str = Field(default="", description="표시번호")
    receipt_date: str = Field(default="", description="접수일자")
    location: str = Field(default="", description="소재지번")
    land_type: str = Field(default="", description="지목 (예: '대', '전', '답')")
    area: str = Field(default="", description="면적")
    cause_and_other: str = Field(default="", description="등기원인 및 기타사항")
    is_cancelled: bool = Field(default=False, description="말소 여부")


class BuildingTitleEntry(BaseModel):
    """표제부 — 건물의 표시 항목"""
    display_number: str = Field(default="", description="표시번호")
    receipt_date: str = Field(default="", description="접수일자")
    location_or_number: str = Field(default="", description="소재지번 또는 건물번호")
    building_detail: str = Field(default="", description="건물내역 (구조, 용도, 면적)")
    cause_and_other: str = Field(default="", description="등기원인 및 기타사항")
    is_cancelled: bool = Field(default=False, description="말소 여부")


class ExclusivePartEntry(BaseModel):
    """표제부 — 전유부분의 건물의 표시 (집합건물)"""
    display_number: str = Field(default="", description="표시번호")
    receipt_date: str = Field(default="", description="접수일자")
    building_number: str = Field(default="", description="건물번호 (동·호)")
    building_detail: str = Field(default="", description="건물내역")
    cause_and_other: str = Field(default="", description="등기원인 및 기타사항")
    is_cancelled: bool = Field(default=False, description="말소 여부")


class LandRightEntry(BaseModel):
    """표제부 — 대지권의 목적인 토지의 표시"""
    display_number: str = Field(default="", description="표시번호")
    location: str = Field(default="", description="소재지번")
    land_type: str = Field(default="", description="지목")
    area: str = Field(default="", description="면적")
    cause_and_other: str = Field(default="", description="등기원인 및 기타사항")


class LandRightRatioEntry(BaseModel):
    """표제부 — 대지권의 표시"""
    display_number: str = Field(default="", description="표시번호")
    land_right_type: str = Field(default="", description="대지권 종류 (예: '소유권')")
    land_right_ratio: str = Field(default="", description="대지권 비율 (예: '15300분의 34.56')")
    cause_and_other: str = Field(default="", description="등기원인 및 기타사항")
    is_cancelled: bool = Field(default=False, description="말소 여부")


class TitleInfo(BaseModel):
    """표제부 정보"""
    unique_number: str = Field(description="고유번호 (예: '1101-2006-000001')")
    property_type: str = Field(description="부동산 유형: 'land'(토지), 'building'(건물), 'aggregate_building'(집합건물)")
    address: str = Field(description="소재지 주소 (지번주소)")
    road_address: Optional[str] = Field(default=None, description="도로명주소")
    building_name: Optional[str] = Field(default=None, description="건물명 (집합건물)")
    structure: Optional[str] = Field(default=None, description="구조 (예: '철근콘크리트조')")
    roof_type: Optional[str] = Field(default=None, description="지붕 종류")
    floors: Optional[int] = Field(default=None, description="층수")
    building_type: Optional[str] = Field(default=None, description="건물 용도 (예: '아파트', '단독주택')")
    areas: List[FloorArea] = Field(default=[], description="층별 면적 목록")
    land_right_ratio: Optional[str] = Field(default=None, description="대지권 비율")
    exclusive_area: Optional[float] = Field(default=None, description="전용면적 (㎡)")
    total_floor_area: Optional[float] = Field(default=None, description="연면적 (㎡)")
    land_type: Optional[str] = Field(default=None, description="지목 (토지)")
    land_area: Optional[str] = Field(default=None, description="토지 면적")
    land_entries: List[LandTitleEntry] = Field(default=[], description="토지 표시 항목 목록")
    building_entries: List[BuildingTitleEntry] = Field(default=[], description="건물 표시 항목 목록")
    exclusive_part_entries: List[ExclusivePartEntry] = Field(default=[], description="전유부분 항목 목록 (집합건물)")
    land_right_entries: List[LandRightEntry] = Field(default=[], description="대지권 목적 토지 목록")
    land_right_ratio_entries: List[LandRightRatioEntry] = Field(default=[], description="대지권 비율 항목 목록")


class TradeListItem(BaseModel):
    """매매목록 — 개별 부동산 항목"""
    serial_number: str = Field(default="", description="일련번호")
    property_description: str = Field(default="", description="부동산의 표시 (예: '[토지] 경상북도 문경시 농암면 내서리 733')")
    rank_number: str = Field(default="", description="순위번호")
    registration_cause: str = Field(default="", description="등기원인 (예비란)")
    correction_cause: str = Field(default="", description="경정원인 (예비란)")


class TradeList(BaseModel):
    """매매목록"""
    list_number: str = Field(default="", description="목록번호 (예: '2016-553')")
    trade_amount: Optional[int] = Field(default=None, description="거래가액 (원)")
    items: List[TradeListItem] = Field(default=[], description="매매 대상 부동산 목록")


class RegistryData(BaseModel):
    """등기부등본 파싱 결과"""
    unique_number: str = Field(description="고유번호")
    property_type: str = Field(description="부동산 유형: 'land', 'building', 'aggregate_building'")
    property_address: str = Field(description="소재지 주소")
    title_info: TitleInfo = Field(description="표제부 정보")
    section_a: List[SectionAEntry] = Field(default=[], description="갑구 항목 목록 (소유권 관련)")
    section_b: List[SectionBEntry] = Field(default=[], description="을구 항목 목록 (소유권 이외 권리)")
    trade_lists: List[TradeList] = Field(default=[], description="매매목록 (복수 가능)")
    raw_text: Optional[str] = Field(default=None, description="전체 원본 텍스트")
    parse_date: str = Field(description="파싱 일시")
    parser_version: Optional[str] = Field(default=None, description="파서 버전 (예: '1.0.1')")
    section_a_count: int = Field(default=0, description="갑구 전체 항목 수")
    section_b_count: int = Field(default=0, description="을구 전체 항목 수")
    active_section_a_count: int = Field(default=0, description="갑구 유효(말소되지 않은) 항목 수")
    active_section_b_count: int = Field(default=0, description="을구 유효(말소되지 않은) 항목 수")
    errors: List[str] = Field(default=[], description="파싱 중 발생한 경고/오류 메시지")


class ParseRequest(BaseModel):
    webhook_url: Optional[str] = Field(default=None, description="파싱 완료 시 결과를 전송할 Webhook URL")
    demo_mode: bool = Field(default=False, description="데모 모드 — 개인정보 마스킹 강화, 결과 일부만 반환")


class ParseResponse(ResponseBase):
    request_id: str = Field(description="요청 고유 ID")
    status: str = Field(description="처리 상태: 'completed', 'failed'")
    data: Optional[RegistryData] = Field(default=None, description="파싱 결과 데이터")
    error: Optional[str] = Field(default=None, description="오류 메시지")
    is_demo: bool = Field(default=False, description="데모 모드 여부")
    remaining_credits: int = Field(default=0, description="잔여 크레딧")


class ParseHistoryItem(BaseModel):
    id: int
    file_name: str
    status: str
    unique_number: Optional[str]
    property_address: Optional[str]
    section_a_count: int
    section_b_count: int
    created_at: datetime
    completed_at: Optional[datetime]
    processing_time: Optional[float]

    class Config:
        from_attributes = True


class ParseHistoryResponse(ResponseBase):
    items: List[ParseHistoryItem]
    total: int
    page: int
    page_size: int
