# PDF 파서 플러그인 개발 가이드

## 요약

1. `parsers/<document_type>/v1_0_0.py`에 `BaseParser` 구현체 작성
2. `parsers/<document_type>/__init__.py`에 `PARSER_CLASSES` export
3. `python tools/benchmark.py --type <document_type> upload/*.pdf`로 검증

---

## 구현해야 할 인터페이스

```python
# parsers/base.py

@dataclass
class DocumentTypeInfo:
    type_id: str              # "building_register"
    display_name: str         # "건축물대장"
    description: str
    sub_types: List[str] = field(default_factory=list)

@dataclass
class ParseResult:
    document_type: str                                    # "building_register"
    document_sub_type: str = ""
    parser_version: str = ""
    data: Dict[str, Any] = field(default_factory=dict)    # 구조화된 파싱 결과
    raw_text: str = ""
    errors: List[str] = field(default_factory=list)
    confidence: float = 1.0

class BaseParser(ABC):
    @classmethod @abstractmethod
    def document_type_info(cls) -> DocumentTypeInfo: ...

    @classmethod @abstractmethod
    def parser_version(cls) -> str: ...

    @classmethod @abstractmethod
    def can_parse(cls, pdf_buffer: bytes, text_sample: str) -> float:
        """0.0~1.0 confidence. 텍스트 첫 2000자에서 키워드로 판별."""
        ...

    @abstractmethod
    def parse(self, pdf_buffer: bytes) -> ParseResult: ...

    def mask_for_demo(self, data: Dict[str, Any]) -> Dict[str, Any]:
        return data  # 필요 시 오버라이드
```

---

## 파일 구조 (예: 건축물대장)

```
parsers/building_register/
├── __init__.py     ← PARSER_CLASSES = [BuildingRegisterParserV1]
└── v1_0_0.py       ← BaseParser 구현체
```

### __init__.py

```python
from parsers.building_register.v1_0_0 import BuildingRegisterParserV1
PARSER_CLASSES = [BuildingRegisterParserV1]
```

### v1_0_0.py (골격)

```python
import io, re
from typing import Dict, Any
import pdfplumber
from parsers.base import BaseParser, DocumentTypeInfo, ParseResult

class BuildingRegisterParserV1(BaseParser):

    @classmethod
    def document_type_info(cls) -> DocumentTypeInfo:
        return DocumentTypeInfo(
            type_id="building_register",
            display_name="건축물대장",
            description="건축물대장 (일반/집합)",
            sub_types=["general", "aggregate"],
        )

    @classmethod
    def parser_version(cls) -> str:
        return "1.0.0"

    @classmethod
    def can_parse(cls, pdf_buffer: bytes, text_sample: str) -> float:
        score = 0.0
        for keyword, weight in [('건축물대장', 0.4), ('대지위치', 0.2), ('건축면적', 0.2)]:
            if keyword in text_sample:
                score += weight
        return min(score, 1.0)

    def parse(self, pdf_buffer: bytes) -> ParseResult:
        with pdfplumber.open(io.BytesIO(pdf_buffer)) as pdf:
            # TODO: 파싱 로직 구현
            raw_text = "\n".join(p.extract_text() or "" for p in pdf.pages)

        return ParseResult(
            document_type="building_register",
            parser_version=self.parser_version(),
            data={...},           # 구조화된 결과
            raw_text=raw_text,
        )
```

---

## 사용 가능한 공유 유틸리티

```python
from parsers.common.pdf_utils import filter_watermark, clean_text, clean_cell
from parsers.common.text_utils import parse_amount, parse_date_korean, parse_resident_number, to_dict
from parsers.common.cancellation import CancellationDetector
```

| 함수 | 용도 |
|------|------|
| `filter_watermark(page)` | pdfplumber 페이지에서 회색 워터마크 제거 |
| `clean_text(text)` | 공백 정규화 + 워터마크 텍스트 제거 |
| `parse_amount("금1,000원")` | → `1000` (int) |
| `parse_date_korean("2025년1월3일")` | → `"2025년 01월 03일"` |
| `CancellationDetector` | 빨간 선/글자 기반 말소 감지 |

---

## 검증

```bash
# 파서 자동 발견 확인
python tools/benchmark.py --list

# 벤치마크 실행
python tools/benchmark.py --type building_register upload/*.pdf

# 파싱 결과 확인
python tools/cli.py --type building_register upload/sample.pdf --json
```
