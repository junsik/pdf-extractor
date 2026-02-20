// 등기부등본 관련 타입 정의

export interface RegistryTitleInfo {
  // 표제부 - 건물의 표시
  uniqueNumber: string; // 고유번호
  propertyType: 'building' | 'aggregate_building'; // 건물 | 집합건물
  address: string; // 소재지번
  roadAddress?: string; // 도로명주소
  buildingName?: string; // 건물명칭
  structure: string; // 구조
  roofType: string; // 지붕
  floors: number; // 층수
  buildingType: string; // 건물종류
  areas: FloorArea[]; // 층별 면적
  landRights?: LandRight[]; // 대지권 (집합건물)
  exclusiveArea?: number; // 전유부분 면적 (집합건물)
  landRightRatio?: string; // 대지권 비율 (집합건물)
}

export interface FloorArea {
  floor: string; // 층
  area: number; // 면적 (㎡)
  isExcluded?: boolean; // 연면적 제외 여부
}

export interface LandRight {
  // 대지권의 목적인 토지의 표시
  address: string; // 소재지번
  landType: string; // 지목
  area: number; // 면적
}

export interface SectionAEntry {
  // 갑구 - 소유권에 관한 사항
  rankNumber: string; // 순위번호
  registrationType: string; // 등기목적
  receiptDate: string; // 접수
  receiptNumber: string; // 접수번호
  registrationCause: string; // 등기원인
  registrationCauseDate?: string; // 등기원인일자
  owners: OwnerInfo[]; // 소유자 목록 (단독: 1명, 공유: N명)
  creditor?: CreditorInfo; // 채권자 정보 (경매, 가압류 등)
  claimAmount?: number; // 청구금액 (가압류)
  restriction?: string; // 금지사항
  isCancelled?: boolean; // 말소 여부
  cancelledByRank?: string; // [수동] 이 항목을 말소시킨 순위번호
  cancellationDate?: string; // 말소일자
  cancellationCause?: string; // 말소원인
  cancelsRank?: string; // [능동] 이 항목이 말소하는 대상 순위번호
  remarks?: string; // 기타사항 (법조문 등)
}

export interface OwnerInfo {
  name: string; // 성명
  residentNumber?: string; // 주민등록번호 (마스킹)
  address?: string; // 주소
  share?: string; // 지분
}

export interface CreditorInfo {
  name: string; // 성명/상호
  residentNumber?: string; // 주민등록번호/법인번호
  address?: string; // 주소
}

export interface SectionBEntry {
  // 을구 - 소유권 이외의 권리에 관한 사항
  rankNumber: string; // 순위번호
  registrationType: string; // 등기목적
  receiptDate: string; // 접수
  receiptNumber: string; // 접수번호
  registrationCause: string; // 등기원인
  registrationCauseDate?: string; // 등기원인일자
  
  // 근저당권 관련
  maxClaimAmount?: number; // 채권최고액
  debtor?: OwnerInfo; // 채무자
  mortgagee?: CreditorInfo; // 근저당권자
  
  // 임차권 관련
  depositAmount?: number; // 임차보증금
  monthlyRent?: number; // 차임 (월세)
  leaseTerm?: LeaseTermInfo; // 임대차 정보
  lessee?: LesseeInfo; // 임차권자
  leaseArea?: string; // 임차 범위
  
  // 전세권 관련
  jeonseDeposit?: number; // 전세보증금
  jeonseRightHolder?: CreditorInfo; // 전세권자
  
  // 공통
  isCancelled?: boolean; // 말소 여부
  cancellationInfo?: string; // 말소 정보
}

export interface LeaseTermInfo {
  contractDate: string; // 임대차계약일자
  residentRegistrationDate?: string; // 주민등록일자
  possessionStartDate?: string; // 점유개시일자
  fixedDate?: string; // 확정일자
}

export interface LesseeInfo {
  name: string; // 성명
  residentNumber?: string; // 주민등록번호 (마스킹)
  address?: string; // 주소
}

export interface TradeListItem {
  serial_number: string; // 일련번호
  property_description: string; // 부동산의 표시
  rank_number: string; // 순위번호
  registration_cause: string; // 등기원인
  correction_cause: string; // 경정원인
}

export interface TradeList {
  list_number: string; // 목록번호
  trade_amount?: number; // 거래가액 (원)
  items: TradeListItem[]; // 매매 대상 부동산
}

export interface RegistrySummary {
  // 주요 등기사항 요약
  ownershipStatus: OwnershipStatus[];
  ownershipOtherMatters: SectionAEntry[];
  mortgagesAndJeonse: SectionBEntry[];
}

export interface OwnershipStatus {
  ownerName: string; // 등기명의인
  residentNumber?: string; // 주민등록번호
  finalShare: string; // 최종지분
  address: string; // 주소
  rankNumber: string; // 순위번호
}

// 전체 등기부등본 데이터
export interface RegistryData {
  uniqueNumber: string; // 고유번호
  propertyType: 'building' | 'aggregate_building'; // 건물 | 집합건물
  propertyAddress: string; // 부동산 주소
  titleInfo: RegistryTitleInfo; // 표제부
  sectionA: SectionAEntry[]; // 갑구
  sectionB: SectionBEntry[]; // 을구
  trade_lists?: TradeList[]; // 매매목록 (복수 가능)
  summary?: RegistrySummary; // 요약 (있는 경우)
  rawText: string; // 원본 텍스트 (참고용)
  parseDate: string; // 파싱 일시
}

// 파싱 요청
export interface ParseRequest {
  fileBuffer: Buffer;
  fileName: string;
  isPaid: boolean; // 유료 여부
  webhookUrl?: string; // Webhook URL
}

// 파싱 응답
export interface ParseResponse {
  success: boolean;
  data?: RegistryData;
  error?: string;
  requestId: string;
  isDemo: boolean; // 데모 버전 여부
}

// Webhook 페이로드
export interface WebhookPayload {
  event: 'parsing.completed' | 'parsing.failed';
  timestamp: string;
  data: {
    requestId: string;
    status: 'success' | 'failed';
    downloadUrl?: string;
    summary?: Partial<RegistryData>;
    error?: string;
  };
  signature: string; // HMAC 서명
}

// API 응답 타입
export interface ApiResponse<T> {
  success: boolean;
  data?: T;
  error?: string;
  message?: string;
}
