# 등기부등본 PDF 파서 개발 가이드

> AI 에이전트 또는 개발자가 새로운 파서 버전을 만들기 위한 브리핑 문서

## 미션

한국 등기부등본(등기사항전부증명서) PDF를 입력받아, 표제부/갑구/을구의 모든 정보를 구조화된 JSON으로 추출하는 파서를 개발한다.

**현재 기준선**: v1.0.0 = **58.4/100** (10개 PDF 평균)

## 인터페이스 계약

파서 모듈은 반드시 아래 2개를 export해야 한다:

```python
PARSER_VERSION: str = "3.0.0"  # 시맨틱 버전

def parse_registry_pdf(pdf_buffer: bytes) -> Dict[str, Any]:
    """PDF 바이트를 받아 구조화된 dict 반환"""
    ...
```

- 입력: PDF 파일의 raw bytes
- 출력: `schemas.RegistryData` Pydantic 모델을 만족하는 dict
- 의존성: `pdfplumber`, `PyMuPDF`, `pdf2image` 사용 가능 (requirements.txt에 이미 포함)

## 출력 스키마

`backend/schemas.py`의 `RegistryData` 모델이 **단일 소스**이다. 반환 dict는 이 구조를 정확히 따라야 한다.

### 최상위 구조

```
{
  "unique_number": "1184-2024-012345",      # 고유번호
  "property_type": "building",               # land | building | aggregate_building
  "property_address": "서울특별시 강남구...", # 소재지
  "title_info": { ... },                     # 표제부 (아래 상세)
  "section_a": [ ... ],                      # 갑구 항목 리스트
  "section_b": [ ... ],                      # 을구 항목 리스트
  "raw_text": "...",                         # 추출한 전체 텍스트
  "parse_date": "2026-02-20T...",            # 파싱 일시
  "parser_version": "3.0.0",                 # 파서 버전
  "errors": [],                              # 섹션별 에러 (부분 실패 시)
  "section_a_count": 5,                      # 갑구 항목 수
  "section_b_count": 3,                      # 을구 항목 수
  "active_section_a_count": 3,               # 말소 안 된 갑구
  "active_section_b_count": 1                # 말소 안 된 을구
}
```

### title_info (표제부)

```
{
  "unique_number": "...",
  "property_type": "building",
  "address": "서울특별시 강남구 역삼동 123-4",
  "road_address": "서울특별시 강남구 역삼로 123",   # Optional
  "building_name": "역삼타워",                      # Optional
  "structure": "철근콘크리트구조",                    # Optional
  "roof_type": "콘크리트 지붕",                      # Optional
  "floors": 5,                                      # Optional
  "building_type": "아파트",                         # Optional
  "areas": [                                        # 층별 면적
    { "floor": "1층", "area": 85.5, "is_excluded": false }
  ],
  "total_floor_area": 342.0,
  "land_right_ratio": "10000분의 123",              # 대지권비율 (집합건물)
  "exclusive_area": 84.97,                          # 전유면적 (집합건물)
  "land_type": "대",                                # 지목 (토지)
  "land_area": "330.5㎡",                           # 면적 (토지)
  "land_entries": [ ... ],                          # 토지 표시 항목
  "building_entries": [ ... ],                      # 건물 표시 항목
  "exclusive_part_entries": [ ... ],                # 전유부분 항목
  "land_right_entries": [ ... ],                    # 대지권 목적 토지
  "land_right_ratio_entries": [ ... ]               # 대지권 표시
}
```

### section_a 항목 (갑구)

```
{
  "rank_number": "1",                            # 순위번호
  "registration_type": "소유권이전",               # 등기목적
  "receipt_date": "2024년 01월 03일",              # 접수일자
  "receipt_number": "12345호",                    # 접수번호
  "registration_cause": "매매",                   # 등기원인
  "registration_cause_date": "2024년 01월 01일",  # 등기원인일자
  "owner": { "name": "홍길동", "resident_number": "901234-*******", "address": "서울..." },
  "owners": [ ... ],                             # 복수 소유자
  "creditor": null,                              # 채권자 (가압류 등)
  "claim_amount": null,                          # 청구금액
  "is_cancelled": false,                         # 말소 여부
  "cancellation_rank_number": null,
  "cancellation_date": null,
  "cancellation_cause": null,
  "cancels_rank_number": null,                   # 이 등기가 말소하는 원본 번호
  "raw_text": "소유권이전 2024년 01월..."         # 원본 텍스트
}
```

### section_b 항목 (을구)

```
{
  "rank_number": "1",
  "registration_type": "근저당권설정",
  "receipt_date": "2024년 03월 15일",
  "receipt_number": "54321호",
  "registration_cause": "설정계약",
  "max_claim_amount": 300000000,                  # 채권최고액 (int, 원)
  "debtor": { "name": "홍길동", ... },           # 채무자
  "mortgagee": { "name": "국민은행", ... },       # 근저당권자
  "deposit_amount": null,                         # 임차보증금 (임차권)
  "monthly_rent": null,                           # 차임/월세 (임차권)
  "lease_term": null,                             # 임대차기간 (임차권)
  "lessee": null,                                 # 임차권자
  "is_cancelled": false,
  "cancels_rank_number": null,
  "raw_text": "근저당권설정 2024년..."
}
```

## 등기부등본 PDF 구조

등기부등본은 고정된 테이블 구조를 가진 벡터 PDF이다.

### 문서 구조

```
[헤더] [토지/건물/집합건물] 서울특별시 강남구 역삼동 123-4
       고유번호 1184-2024-012345

[표제부] ─ 토지의 표시 / 1동의 건물의 표시 / 전유부분의 건물의 표시
  ┌──────────┬──────────┬──────────┬──────────┬──────────┐
  │ 표시번호 │  접  수  │ 소재지번 │ 건물내역 │ 등기원인 │
  ├──────────┼──────────┼──────────┼──────────┼──────────┤
  │    1     │ 2024년...│ 역삼동.. │ 철근콘.. │ ...      │
  └──────────┴──────────┴──────────┴──────────┴──────────┘

[갑구] ─ 소유권에 관한 사항
  ┌──────────┬──────────┬──────────┬──────────┬──────────┐
  │ 순위번호 │ 등기목적 │  접  수  │ 등기원인 │ 권리자등 │
  ├──────────┼──────────┼──────────┼──────────┼──────────┤
  │    1     │소유권이전│2024년... │  매매    │소유자 홍.│
  └──────────┴──────────┴──────────┴──────────┴──────────┘

[을구] ─ 소유권 이외의 권리에 관한 사항
  (동일 테이블 구조)

[공동담보목록] ─ 파싱 대상 아님
[매각물건목록] ─ 파싱 대상 아님
```

### 핵심 특징

- **말소**: 붉은 선(가로선/사각형) 또는 붉은 글자로 표시. 말소된 항목도 데이터에 포함하되 `is_cancelled: true`
- **부동산 유형**: `land`(토지), `building`(건물), `aggregate_building`(집합건물) 3종
- **집합건물 전용 섹션**: 전유부분의 건물의 표시, 대지권의 목적인 토지의 표시, 대지권의 표시
- **워터마크**: 회색 "열람용" 텍스트가 겹쳐 있음 → 필터링 필요
- **페이지 연속**: 하나의 테이블이 여러 페이지에 걸칠 수 있음

## 현재 약점 (개선 기회)

v1.0.0 벤치마크에서 빈번하게 누락되는 토큰들:

| 카테고리 | 누락 패턴 | 현재 점수 |
|----------|-----------|-----------|
| **주소 파싱** | 시/도/군/구/동 등 주소 토큰 (서울특별시, 관악구, 봉천동...) | 낮음 |
| **금액** | `000원`, `채권최고액`, `전세금`, `임차보증금` | 을구 51.9 |
| **인물** | `채무자`, `채권자`, `소유자` + 이름 | 갑구 59.2 |
| **등기원인 상세** | `전산이기`, `규정에 의하여`, `결정` 등 변형 | 전반 |
| **지번/번지** | 숫자 지번 (380, 645, 1644 등) | 표제부 59.5 |

**섹션별 점수**: 표제부 59.5 / 갑구 59.2 / 을구 51.9

## 파일 위치

```
backend/
├── pdf_parser.py           # 래퍼 (버전 스위칭만 담당, 구현 없음)
├── parsers/
│   ├── __init__.py         # load_parser(), list_parsers()
│   ├── template.py         # 새 파서 시작점 (이 파일을 복사)
│   └── v1_0_0.py           # v1.0.0 기준선 (58.4/100)
├── schemas.py              # 출력 스키마 (RegistryData 등)
├── benchmark.py            # 벤치마크 CLI
└── analyze_pdf.py          # PDF 구조 분석 도구
```

`pdf_parser.py`는 thin wrapper이다. 실제 파서는 `parsers/v*.py`에 있고, `pdf_parser.py`의 `ACTIVE_VERSION`으로 서비스에서 사용할 버전을 지정한다.

## 개발 워크플로우

```bash
# 1. 템플릿 복사
cp backend/parsers/template.py backend/parsers/v1_1_0.py

# 2. 구현 (PARSER_VERSION = "1.1.0")
#    - pdfplumber로 PDF 열기
#    - 테이블 추출 + 텍스트 추출
#    - 구조화하여 dict 반환

# 3. PDF 구조 확인 (필요 시)
cd backend && uv run python analyze_pdf.py

# 4. 벤치마크 실행
uv run python benchmark.py --parser v1.1.0

# 5. 기존 버전과 비교
uv run python benchmark.py --all-parsers

# 6. 점수가 올랐으면 저장
uv run python benchmark.py --parser v1.1.0 --save

# 7. 서비스에 적용 (pdf_parser.py의 ACTIVE_VERSION 변경)
#    ACTIVE_VERSION = "v1.1.0"
#    또는 환경변수: PARSER_VERSION=v1.1.0
```

## 사용 가능한 라이브러리

| 라이브러리 | 용도 | import |
|-----------|------|--------|
| pdfplumber | 테이블/텍스트/선/문자 추출 | `import pdfplumber` |
| PyMuPDF (fitz) | 대체 PDF 처리, OCR 지원 | `import fitz` |
| pdf2image | PDF→이미지 변환 (OCR 전처리) | `from pdf2image import convert_from_bytes` |

## 제약사항

- `parse_registry_pdf(bytes) -> Dict` 시그니처는 변경 불가
- 출력은 `schemas.RegistryData`를 만족해야 함
- 새 필드가 필요하면 `schemas.py` 변경을 별도 요청
- 외부 API 호출 금지 (오프라인 파싱만)
- 신규 pip 패키지 설치 금지 (기존 requirements.txt 범위 내)
