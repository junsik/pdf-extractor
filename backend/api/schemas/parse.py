"""PDF 파싱 관련 스키마"""
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel
from api.schemas.common import ResponseBase


class FloorArea(BaseModel):
    floor: str
    area: float
    is_excluded: bool = False


class OwnerInfo(BaseModel):
    name: str
    resident_number: Optional[str] = None
    address: Optional[str] = None
    share: Optional[str] = None


class CreditorInfo(BaseModel):
    name: str
    resident_number: Optional[str] = None
    address: Optional[str] = None


class LesseeInfo(BaseModel):
    name: str
    resident_number: Optional[str] = None
    address: Optional[str] = None


class LeaseTermInfo(BaseModel):
    contract_date: Optional[str] = None
    resident_registration_date: Optional[str] = None
    possession_start_date: Optional[str] = None
    fixed_date: Optional[str] = None


class CancellationInfo(BaseModel):
    is_cancelled: bool = False
    cancellation_rank_number: Optional[str] = None
    cancellation_date: Optional[str] = None
    cancellation_cause: Optional[str] = None
    cancels_rank_number: Optional[str] = None


class SectionAEntry(BaseModel):
    rank_number: str
    registration_type: str
    receipt_date: str
    receipt_number: str
    registration_cause: Optional[str] = None
    registration_cause_date: Optional[str] = None
    owner: Optional[OwnerInfo] = None
    creditor: Optional[CreditorInfo] = None
    claim_amount: Optional[int] = None
    is_cancelled: bool = False
    cancellation_rank_number: Optional[str] = None
    cancellation_date: Optional[str] = None
    cancellation_cause: Optional[str] = None
    cancels_rank_number: Optional[str] = None
    raw_text: Optional[str] = None


class SectionBEntry(BaseModel):
    rank_number: str
    registration_type: str
    receipt_date: str
    receipt_number: str
    registration_cause: Optional[str] = None
    registration_cause_date: Optional[str] = None
    max_claim_amount: Optional[int] = None
    debtor: Optional[OwnerInfo] = None
    mortgagee: Optional[CreditorInfo] = None
    deposit_amount: Optional[int] = None
    monthly_rent: Optional[int] = None
    lease_term: Optional[LeaseTermInfo] = None
    lessee: Optional[LesseeInfo] = None
    lease_area: Optional[str] = None
    is_cancelled: bool = False
    cancellation_rank_number: Optional[str] = None
    cancellation_date: Optional[str] = None
    cancellation_cause: Optional[str] = None
    cancels_rank_number: Optional[str] = None
    raw_text: Optional[str] = None


class LandTitleEntry(BaseModel):
    display_number: str = ""
    receipt_date: str = ""
    location: str = ""
    land_type: str = ""
    area: str = ""
    cause_and_other: str = ""
    is_cancelled: bool = False


class BuildingTitleEntry(BaseModel):
    display_number: str = ""
    receipt_date: str = ""
    location_or_number: str = ""
    building_detail: str = ""
    cause_and_other: str = ""
    is_cancelled: bool = False


class ExclusivePartEntry(BaseModel):
    display_number: str = ""
    receipt_date: str = ""
    building_number: str = ""
    building_detail: str = ""
    cause_and_other: str = ""
    is_cancelled: bool = False


class LandRightEntry(BaseModel):
    display_number: str = ""
    location: str = ""
    land_type: str = ""
    area: str = ""
    cause_and_other: str = ""


class LandRightRatioEntry(BaseModel):
    display_number: str = ""
    land_right_type: str = ""
    land_right_ratio: str = ""
    cause_and_other: str = ""
    is_cancelled: bool = False


class TitleInfo(BaseModel):
    unique_number: str
    property_type: str
    address: str
    road_address: Optional[str] = None
    building_name: Optional[str] = None
    structure: Optional[str] = None
    roof_type: Optional[str] = None
    floors: Optional[int] = None
    building_type: Optional[str] = None
    areas: List[FloorArea] = []
    land_right_ratio: Optional[str] = None
    exclusive_area: Optional[float] = None
    total_floor_area: Optional[float] = None
    land_type: Optional[str] = None
    land_area: Optional[str] = None
    land_entries: List[LandTitleEntry] = []
    building_entries: List[BuildingTitleEntry] = []
    exclusive_part_entries: List[ExclusivePartEntry] = []
    land_right_entries: List[LandRightEntry] = []
    land_right_ratio_entries: List[LandRightRatioEntry] = []


class RegistryData(BaseModel):
    unique_number: str
    property_type: str
    property_address: str
    title_info: TitleInfo
    section_a: List[SectionAEntry] = []
    section_b: List[SectionBEntry] = []
    raw_text: Optional[str] = None
    parse_date: str
    parser_version: Optional[str] = None
    section_a_count: int = 0
    section_b_count: int = 0
    active_section_a_count: int = 0
    active_section_b_count: int = 0
    errors: List[str] = []


class ParseRequest(BaseModel):
    webhook_url: Optional[str] = None
    demo_mode: bool = False


class ParseResponse(ResponseBase):
    request_id: str
    status: str
    data: Optional[RegistryData] = None
    error: Optional[str] = None
    is_demo: bool = False
    remaining_credits: int = 0


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
