# 등기부등본 PDF 파서

한국 부동산 등기부등본(등기사항전부증명서) PDF를 구조화된 JSON으로 변환하는 파서 엔진.

## 지원 부동산 유형

| 유형 | property_type | 표제부 |
|------|--------------|--------|
| 토지 | `land` | 토지의 표시 (지목, 면적) |
| 건물 | `building` | 1동의 건물의 표시 (구조, 지붕, 층수, 면적) |
| 집합건물 | `aggregate_building` | 1동 + 전유부분 + 대지권 |

## 설치

```bash
# uv 설치 (없는 경우)
pip install uv

# 의존성 설치
cd backend
uv sync
```

### 의존성

- Python 3.12+
- pdfplumber - PDF 테이블/텍스트 추출
- PyMuPDF - PDF 이미지 변환 (검증용)

## CLI 사용법

```bash
# 프로젝트 루트에서 실행
cd c:\work\pdf-service

# 단일 PDF 상세 출력
uv run --project backend python backend/cli.py upload/파일명.pdf

# 전체 PDF 요약
uv run --project backend python backend/cli.py "upload/*.pdf" --summary

# 특정 섹션만 출력
uv run --project backend python backend/cli.py upload/파일명.pdf --section 갑구
uv run --project backend python backend/cli.py upload/파일명.pdf --section 을구
uv run --project backend python backend/cli.py upload/파일명.pdf --section 표제부

# JSON 출력
uv run --project backend python backend/cli.py upload/파일명.pdf --json

# JSON 파일로 저장
uv run --project backend python backend/cli.py upload/파일명.pdf --json > output.json
```

### CLI 옵션

| 옵션 | 설명 |
|------|------|
| (없음) | 전체 상세 출력 |
| `--summary` | 파일당 한줄 요약 (종류, 주소, 건수) |
| `--json` | JSON 형식 출력 |
| `--section 갑구` | 갑구만 출력 (`을구`, `표제부` 가능) |

## API 서버

```bash
cd backend
uv run uvicorn main:app --reload --port 8000
```

`POST /api/parse` - PDF 파일 업로드 후 파싱 결과 반환

## 출력 구조

```
{
  "unique_number": "1350-1996-047446",    // 고유번호
  "property_type": "land",                // land | building | aggregate_building
  "property_address": "경기도 안산시...",    // 주소

  "title_info": {                          // 표제부
    "land_type": "임야",                   // 지목 (토지)
    "land_area": "830㎡",                  // 면적 (토지, 최신값)
    "building_type": "아파트",              // 건물종류 (건물/집합)
    "structure": "철근콘크리트구조",          // 구조
    "exclusive_area": 84.97,               // 전유면적 (집합건물)
    "land_right_ratio": "10098분의 128",    // 대지권비율 (집합건물)
    "road_address": "서울시...",            // 도로명주소
    ...
  },

  "section_a": [...],                      // 갑구 (소유권)
  "section_a_count": 17,
  "active_section_a_count": 14,

  "section_b": [...],                      // 을구 (소유권 이외)
  "section_b_count": 6,
  "active_section_b_count": 4
}
```

### 갑구 항목 (section_a)

```
{
  "rank_number": "3",               // 순위번호
  "registration_type": "소유권이전",   // 등기목적
  "receipt_date": "2012년3월27일",    // 접수일
  "receipt_number": "제26092호",      // 접수번호
  "is_cancelled": false,             // 말소 여부
  "cancels_rank_number": null,       // 말소 대상 번호
  "owners": [{                       // 소유자 목록
    "name": "김점숙",
    "resident_number": "590109-*******",
    "address": "인천광역시...",
    "share": "2분의 1"
  }],
  "creditor": null,                  // 채권자 (가압류 등)
  "claim_amount": 277000000          // 청구/거래금액
}
```

### 을구 항목 (section_b)

```
{
  "rank_number": "1",               // 순위번호
  "registration_type": "근저당권설정",  // 등기목적
  "receipt_date": "2013년8월30일",    // 접수일
  "is_cancelled": true,              // 말소 여부
  "cancels_rank_number": null,       // 말소 대상 번호
  "mortgagee": {                     // 근저당권자/전세권자
    "name": "옹진수산업협동조합",
    "resident_number": "124138-0000274"
  },
  "max_claim_amount": 949000000,     // 채권최고액
  "purpose": null                    // 목적 (지상권 등)
}
```

## 파서 구조

```
pdf_parser.py
├── _filter_watermark()         # pdfplumber 레벨 워터마크(회색문자) 필터링
├── CancellationDetector        # 빨간 선/문자 기반 말소 감지
│   ├── analyze_page()          #   페이지 lines/chars 색상 분석
│   └── is_row_cancelled()      #   행 좌표 기반 말소 판정
└── RegistryPDFParser
    ├── parse()                 # 메인 파싱 루프
    │   ├── 워터마크 필터링       #   _filter_watermark(page)
    │   ├── 섹션 감지            #   SECTION_PATTERNS 매칭
    │   ├── 테이블 추출           #   clean_page.extract_tables()
    │   └── 말소 관계 매핑        #   _map_cancellations()
    ├── _parse_title_*()         # 표제부 파싱 (토지/건물/집합)
    ├── _parse_section_a_*()     # 갑구 파싱
    └── _parse_section_b_*()     # 을구 파싱
```

### 핵심 처리

- **워터마크 제거**: pdfplumber 문자 레벨에서 회색(RGB > 0.5) 문자 필터링. PDF 열 때 1회 적용
- **말소 감지**: 빨간 선(page.lines)과 빨간 문자(page.chars) 분석으로 행 단위 말소 판정
- **크로스페이지 병합**: 순위번호가 빈 행은 이전 항목의 연속으로 합침
- **섹션 분류**: 테이블 헤더 패턴 매칭으로 표제부/갑구/을구/공동담보/요약 구분
- **요약 섹션 필터링**: `__skip__` 패턴으로 공동담보목록, 매각물건목록, 주요등기사항요약 제외

## 파일 목록

| 파일 | 설명 |
|------|------|
| `pdf_parser.py` | 파서 엔진 (메인) |
| `cli.py` | CLI 도구 (디버깅/검증용) |
| `main.py` | FastAPI 서버 |
| `test_parser.py` | 배치 테스트 스크립트 |
| `analyze_pdf.py` | PDF 구조 분석 도구 |
| `schemas.py` | Pydantic 스키마 |
