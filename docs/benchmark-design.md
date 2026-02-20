# PDF 파서 벤치마크 설계 문서

## 개요

등기부등본 PDF 파서의 정확도를 버전별로 수치화하여 추적하는 시스템이다. LLM 벤치마크처럼 단일 점수(0~100)로 파서 품질을 표현한다.

**핵심 원칙**: PDF에서 추출 가능한 모든 텍스트를 빠짐없이 구조화하면 100점.

## 아키텍처

```
upload/*.pdf ──┬──→ [Ground Truth 추출] ──→ 토큰 셋 (기대값)
               │                                 │
               └──→ [파서 실행] ──→ 토큰 셋 (실제값)
                                                 │
                              토큰 리콜 계산 ←────┘
                                    │
                              점수 (0~100)
```

### 파일 구조

| 파일 | 역할 |
|------|------|
| `backend/pdf_parser.py` | 래퍼 (버전 스위칭 + `mask_for_demo`) |
| `backend/parsers/__init__.py` | 파서 버전 로더 (`load_parser`, `list_parsers`) |
| `backend/parsers/v*_*_*.py` | 버전별 파서 구현 (예: `v1_0_0.py`) |
| `backend/parsers/template.py` | 새 파서 시작점 |
| `benchmark-history.json` | 버전별 점수 누적 (JSON 배열) |
| `BENCHMARK.md` | 최근 5개 버전 비교 리포트 (자동 생성) |
| `upload/*.pdf` | 테스트 코퍼스 (10개 PDF) |

### 인터페이스 계약

모든 파서 모듈(`parsers/v*.py`)은 아래 2개를 반드시 export한다:

| 이름 | 타입 | 설명 |
|------|------|------|
| `parse_registry_pdf` | `(bytes) -> Dict[str, Any]` | PDF 바이트를 받아 구조화된 dict 반환 |
| `PARSER_VERSION` | `str` | 엔진 버전 (예: `"1.0.0"`) |

`pdf_parser.py`는 thin wrapper로, `parsers/` 패키지에서 활성 버전을 로드한다:

```python
# pdf_parser.py (래퍼)
ACTIVE_VERSION = os.environ.get("PARSER_VERSION", "v1.0.0")
_parser = load_parser(ACTIVE_VERSION)
PARSER_VERSION = _parser.PARSER_VERSION
parse_registry_pdf = _parser.parse_registry_pdf
```

벤치마크에서 특정 버전을 직접 로드할 수도 있다:

```python
from parsers import load_parser
parser = load_parser("v1.0.0")
result = parser.parse_registry_pdf(pdf_bytes)
```

### 출력 스키마

파서의 반환 dict는 `schemas.RegistryData` (Pydantic 모델)을 만족해야 한다. 이 모델이 **파서 출력의 단일 소스**이다.

- 파서 내부 구현은 자유 (dataclass, dict, 어떤 방식이든)
- 최종 반환 dict가 `schemas.RegistryData`를 만족하면 됨
- 파서 버전이 올라가면서 새 필드가 필요하면 `schemas.py`를 먼저 확장

### 파서 버전 관리

```
parsers/template.py ──복사──→ parsers/v1_1_0.py ──구현──→ 벤치마크 ──→ 서비스 적용
```

1. `cp parsers/template.py parsers/v1_1_0.py`
2. 구현 (`PARSER_VERSION = "1.1.0"`)
3. 벤치마크: `uv run python benchmark.py --parser v1.1.0 --save`
4. 서비스 적용: `pdf_parser.py`의 `ACTIVE_VERSION = "v1.1.0"` 또는 환경변수 `PARSER_VERSION=v1.1.0`

## 스코어링 방식

### 1단계: Ground Truth 추출

PDF를 pdfplumber로 열어 **사람이 읽을 수 있는 모든 텍스트**를 추출한다.

```
PDF ──→ pdfplumber ──→ 워터마크 제거 ──→ 헤더/푸터 제거 ──→ 스킵 섹션 제거 ──→ Ground Truth
```

**제거 대상** (이것들은 파서가 캡처하지 않아도 감점하지 않음):

| 제거 항목 | 이유 |
|-----------|------|
| 워터마크 (`열람용`) | 회색 문자, 콘텐츠 아님 |
| 헤더 (`[건물] 서울시...`, `표시번호 접수...`) | 페이지 반복 구조 |
| 푸터 (`열람일시:`, `1/5`) | 메타데이터 |
| 공동담보목록, 매각물건목록, 주요등기사항요약 | 파서가 의도적으로 스킵하는 섹션 |
| 컬럼 헤더 토큰 (`표시번호`, `순위번호`, `등기목적` 등) | 테이블 구조, 데이터 아님 |

**섹션 분리**: 동일한 섹션 감지 패턴으로 Ground Truth를 표제부/갑구/을구로 분리한다.

### 2단계: 파서 출력 텍스트 수집

`parse_registry_pdf()` 결과 dict를 재귀 순회하여 **구조화된 필드의 텍스트만** 수집한다.

```
파서 결과 dict ──→ 재귀 순회 ──→ 문자열/숫자 값 수집 ──→ Parser Tokens
```

**제외 키** (이것들은 파서가 "추출"한 게 아니므로 점수에 포함하지 않음):

| 제외 키 | 이유 |
|---------|------|
| `raw_text` | 원본 텍스트 그대로 — 포함하면 항상 ~100점 |
| `parser_version`, `parse_date` | 메타데이터 |
| `errors` | 에러 메시지 |
| `*_count` | 통계 (파생값) |
| `is_cancelled` | boolean |
| `property_type` | 분류값 (`land` 등) |

**숫자 변환**: `max_claim_amount: 300000000` 같은 int 필드는 `"300000000"`, `"300,000,000"` 두 형태로 변환하여 매칭 기회를 준다.

### 3단계: 토큰화

양쪽 텍스트를 동일한 방식으로 토큰화한다:

```python
tokens = re.findall(r"[\w가-힣]+", text)  # 한글+영숫자 단어 추출
tokens = [t for t in tokens if len(t) >= 2]  # 1글자 제거
tokens = [t for t in tokens if t not in NOISE_TOKENS]  # 노이즈 제거
→ Counter (멀티셋)
```

`set`이 아닌 `Counter`를 사용한다. "소유권이전"이 GT에 3번, 파서에 2번 나오면 해당 토큰 리콜은 2/3이다.

### 4단계: 리콜 계산

```
Score = Σ min(GT[token], Parser[token]) / Σ GT[token] × 100
         for all tokens in GT
```

| 예시 | GT | Parser | 기여 |
|------|-----|--------|------|
| "소유권이전" | 3회 | 2회 | 2/3 |
| "근저당권설정" | 1회 | 1회 | 1/1 |
| "홍길동" | 1회 | 0회 | 0/1 |

섹션별로도 동일 계산을 수행하여 표제부/갑구/을구 개별 점수를 산출한다. 해당 섹션이 PDF에 없으면 `N/A`.

## 점수 해석

| 점수 범위 | 의미 |
|-----------|------|
| 90~100 | PDF의 거의 모든 정보가 구조화됨 |
| 70~89 | 주요 정보는 캡처, 일부 누락 |
| 50~69 | 핵심 데이터는 있지만 상당량 누락 |
| 0~49 | 파싱 실패에 가까움 |

## 데이터 관리

### 저장 흐름

```
benchmark.py --save
  ├── 벤치마크 실행 → 콘솔 출력
  ├── benchmark-history.json 에 결과 추가
  └── BENCHMARK.md 자동 재생성 (최근 5개 버전)
```

### benchmark-history.json 구조

```json
[
  {
    "version": "2.1.0",
    "date": "2026-02-20 11:33",
    "files": 10,
    "overall": 58.4,
    "title": 59.5,
    "section_a": 59.2,
    "section_b": 51.9,
    "details": [
      {
        "file": "1484015_18412010002706.pdf",
        "type": "aggregate_building",
        "score": 66.1,
        "title": 97.1,
        "section_a": 53.0,
        "section_b": 49.6,
        "gt_tokens": 1137,
        "parser_tokens": 751
      }
    ]
  }
]
```

- 같은 버전으로 재실행하면 해당 버전 데이터를 **교체** (중복 방지)
- 히스토리는 무한 누적, 리포트는 최근 5개만 표시

### BENCHMARK.md 자동 생성 내용

| 섹션 | 내용 |
|------|------|
| Latest | 최신 버전 요약 |
| Version History | Mermaid xychart-beta 바 차트 (버전별 Overall) |
| Section Breakdown | Mermaid xychart-beta 라인 차트 (표제부/갑구/을구 추이) |
| Score Table | 최근 5개 버전 비교 테이블 |
| File Details | 최신 버전의 파일별 상세 점수 |

Mermaid 차트는 히스토리가 2개 이상일 때만 생성된다.

## CLI 사용법

```bash
cd backend

# 현재 활성 파서(latest)로 벤치마크
uv run python benchmark.py

# 특정 버전으로 벤치마크
uv run python benchmark.py --parser v1.0.0

# 모든 파서 버전 비교
uv run python benchmark.py --all-parsers

# 사용 가능한 파서 목록
uv run python benchmark.py --list

# 특정 PDF만 테스트
uv run python benchmark.py ../upload/1484015_18412010002706.pdf

# 누락 토큰 확인 (파서 개선 포인트 파악)
uv run python benchmark.py --verbose

# 실행 + JSON 저장 + MD 리포트 생성
uv run python benchmark.py --save

# JSON 히스토리에서 MD 리포트만 재생성
uv run python benchmark.py --report
```

## 파서 개선 워크플로우

```
1. cp parsers/template.py parsers/v1_1_0.py
2. 구현 (PARSER_VERSION = "1.1.0")
3. uv run python benchmark.py --parser v1.1.0 --save
4. 점수 확인 → 올랐으면 서비스 적용
5. pdf_parser.py의 ACTIVE_VERSION = "v1.1.0" (또는 환경변수)
6. BENCHMARK.md 가 자동 갱신되어 히스토리 추적
```

## 테스트 코퍼스

`upload/` 폴더의 10개 PDF가 벤치마크 코퍼스를 구성한다.

| 유형 | 파일 수 | 특징 |
|------|---------|------|
| land (토지) | 4 | 토지 표제부, 지목/면적 |
| building (건물) | 2 | 건물 표제부, 구조/층수/면적 |
| aggregate_building (집합건물) | 4 | 전유부분, 대지권, 복합 표제부 |

PDF를 추가/제거하면 점수 기준이 바뀌므로, 코퍼스 변경 시 새 버전으로 기준선을 다시 잡아야 한다.

## 한계와 주의사항

| 한계 | 설명 |
|------|------|
| 토큰 리콜만 측정 | 파서가 잘못된 필드에 값을 넣어도 (예: 소유자 이름을 주소 필드에) 감점 안 됨 |
| 숫자 변환 갭 | `금 3억원` → `300000000` 변환은 토큰이 달라서 매칭 안 될 수 있음 |
| 날짜 정규화 | GT의 `2025.01.03`이 파서에서 `2025년 01월 03일`로 변환되면 토큰이 달라짐 |
| 코퍼스 편향 | 10개 PDF가 모든 등기부 유형을 대표하지 못할 수 있음 |

이 한계들은 인지하되, 현재 단계에서 "파서가 얼마나 많은 정보를 캡처하는가"를 추적하는 데는 충분하다.
