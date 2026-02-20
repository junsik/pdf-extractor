"""
파서 버전 관리 패키지

표준 인터페이스:
  모든 파서 모듈은 아래 2개를 반드시 export해야 한다.

  - PARSER_VERSION: str                              # 버전 문자열
  - parse_registry_pdf(pdf_buffer: bytes) -> Dict    # 파싱 함수

  출력 스키마: schemas.RegistryData (Pydantic 모델)
  파서의 반환 dict는 이 모델로 검증 가능해야 한다.

사용법:
  from parsers import load_parser, list_parsers

  parser = load_parser("v1.0.0")   # 특정 버전
  parser = load_parser("latest")   # pdf_parser.py의 ACTIVE_VERSION
  result = parser.parse_registry_pdf(pdf_bytes)
"""
import importlib
import os
import glob
from pathlib import Path
from typing import Dict, Any, List, Protocol, runtime_checkable


@runtime_checkable
class ParserModule(Protocol):
    """파서 모듈이 구현해야 하는 인터페이스"""
    PARSER_VERSION: str

    def parse_registry_pdf(self, pdf_buffer: bytes) -> Dict[str, Any]: ...


class ParserWrapper:
    """로드된 파서 모듈 래퍼"""

    def __init__(self, module):
        self._module = module
        self.PARSER_VERSION: str = module.PARSER_VERSION
        self.parse_registry_pdf = module.parse_registry_pdf

    def __repr__(self):
        return f"<Parser v{self.PARSER_VERSION}>"


def load_parser(version: str = "latest") -> ParserWrapper:
    """
    파서 버전 로드.

    Args:
        version: "latest" → pdf_parser.py의 ACTIVE_VERSION,
                 "v1.0.0" or "1.0.0" → parsers/v1_0_0.py
    """
    if version == "latest":
        # pdf_parser.py의 ACTIVE_VERSION을 읽어서 해당 버전 로드
        # (순환 import 방지: pdf_parser.py가 이 함수를 호출하므로)
        import os
        active = os.environ.get("PARSER_VERSION", "v1.0.0")
        return load_parser(active)

    # "v1.0.0" → "1.0.0" → "v1_0_0"
    clean = version.lstrip("v")
    module_name = "v" + clean.replace(".", "_")

    try:
        mod = importlib.import_module(f"parsers.{module_name}")
    except ModuleNotFoundError:
        available = list_parsers()
        raise ValueError(
            f"파서 v{clean} 없음. 사용 가능: {', '.join(available)}"
        )

    return ParserWrapper(mod)


def list_parsers() -> List[str]:
    """사용 가능한 파서 버전 목록 반환 (latest 포함)"""
    versions = ["latest"]
    parsers_dir = Path(__file__).parent
    for f in sorted(parsers_dir.glob("v*.py")):
        # v2_1_0.py → "v2.1.0"
        name = f.stem  # "v2_1_0"
        ver = name[1:].replace("_", ".")  # "2.1.0"
        versions.append(f"v{ver}")
    return versions
