"""
멀티 문서 파서 플러그인 레지스트리

디렉토리 구조:
  parsers/
    registry/              # document_type = "registry"
      __init__.py          # PARSER_CLASSES 리스트 export
      v1_0_0.py            # BaseParser 구현체
    building_register/     # document_type = "building_register" (향후)
      __init__.py
      v1_0_0.py
    ...

각 플러그인 디렉토리의 __init__.py는 PARSER_CLASSES: List[Type[BaseParser]]를 export해야 한다.

하위 호환:
  load_parser("v1.0.0")   → get_parser("registry", "1.0.0")
  load_parser("latest")   → get_parser("registry", "latest")
  list_parsers()           → 레거시 버전 목록
"""
import importlib
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Type, Any
from loguru import logger

from parsers.base import BaseParser, DocumentTypeInfo, ParseResult


# ==================== 글로벌 레지스트리 ====================

# {document_type: {version: ParserClass}}
_plugin_registry: Dict[str, Dict[str, Type[BaseParser]]] = {}
_discovered = False


def discover_plugins() -> None:
    """parsers/*/ 디렉토리를 스캔하여 파서 플러그인을 자동 등록"""
    global _discovered
    if _discovered:
        return

    parsers_dir = Path(__file__).parent
    for subdir in sorted(parsers_dir.iterdir()):
        if not subdir.is_dir():
            continue
        if subdir.name.startswith('_') or subdir.name == 'common':
            continue
        init_file = subdir / '__init__.py'
        if not init_file.exists():
            continue

        try:
            module = importlib.import_module(f"parsers.{subdir.name}")
            parser_classes = getattr(module, 'PARSER_CLASSES', [])
            for cls in parser_classes:
                info = cls.document_type_info()
                version = cls.parser_version()
                _plugin_registry.setdefault(info.type_id, {})[version] = cls
                logger.debug(f"파서 등록: {info.type_id} v{version} ({info.display_name})")
        except Exception as e:
            logger.warning(f"파서 플러그인 로드 실패 '{subdir.name}': {e}")

    _discovered = True


def get_parser(document_type: str, version: str = "latest") -> BaseParser:
    """문서 타입과 버전으로 파서 인스턴스 반환"""
    discover_plugins()

    if document_type not in _plugin_registry:
        available = list(_plugin_registry.keys())
        raise ValueError(
            f"알 수 없는 문서 타입 '{document_type}'. 사용 가능: {available}"
        )

    versions = _plugin_registry[document_type]
    if version == "latest":
        sorted_versions = sorted(versions.keys(), key=_version_sort_key)
        version = sorted_versions[-1]
    else:
        version = version.lstrip("v")

    if version not in versions:
        available = sorted(versions.keys(), key=_version_sort_key)
        raise ValueError(
            f"파서 '{document_type}' v{version} 없음. 사용 가능: {available}"
        )

    return versions[version]()


def detect_document_type(pdf_buffer: bytes) -> Tuple[str, float]:
    """PDF의 문서 타입을 자동 감지.

    Returns:
        (document_type_id, confidence) 최고 매칭
    """
    discover_plugins()

    import io
    import pdfplumber

    text_sample = ""
    try:
        with pdfplumber.open(io.BytesIO(pdf_buffer)) as pdf:
            for page in pdf.pages[:2]:
                text_sample += (page.extract_text() or "") + "\n"
        text_sample = text_sample[:2000]
    except Exception:
        pass

    buffer_sample = pdf_buffer[:10240]

    best_type = None
    best_confidence = 0.0

    for doc_type, versions in _plugin_registry.items():
        latest_version = sorted(versions.keys(), key=_version_sort_key)[-1]
        cls = versions[latest_version]
        try:
            confidence = cls.can_parse(buffer_sample, text_sample)
            if confidence > best_confidence:
                best_confidence = confidence
                best_type = doc_type
        except Exception as e:
            logger.warning(f"문서 타입 감지 실패 {doc_type}: {e}")

    if best_type is None or best_confidence < 0.1:
        raise ValueError("문서 타입을 감지할 수 없습니다. 매칭되는 파서가 없습니다.")

    return best_type, best_confidence


def list_document_types() -> List[DocumentTypeInfo]:
    """등록된 모든 문서 타입 정보 반환"""
    discover_plugins()
    result = []
    for doc_type, versions in _plugin_registry.items():
        latest = sorted(versions.keys(), key=_version_sort_key)[-1]
        result.append(versions[latest].document_type_info())
    return result


def list_versions(document_type: str) -> List[str]:
    """특정 문서 타입의 사용 가능한 파서 버전 목록"""
    discover_plugins()
    if document_type not in _plugin_registry:
        return []
    return sorted(_plugin_registry[document_type].keys(), key=_version_sort_key)


def _version_sort_key(v: str) -> Tuple[int, ...]:
    """'1.0.0' → (1, 0, 0) 정렬키"""
    return tuple(int(x) for x in v.lstrip("v").split('.') if x.isdigit())


# ==================== 하위 호환 인터페이스 ====================
# 기존 코드: from parsers import load_parser, list_parsers


class ParserWrapper:
    """레거시 파서 래퍼 (기존 인터페이스 호환)"""

    def __init__(self, parser: BaseParser):
        self._parser = parser
        self.PARSER_VERSION: str = parser.parser_version()

    def parse_registry_pdf(self, pdf_buffer: bytes) -> Dict[str, Any]:
        result = self._parser.parse(pdf_buffer)
        return result.data

    def __repr__(self):
        return f"<Parser v{self.PARSER_VERSION}>"


def load_parser(version: str = "latest") -> ParserWrapper:
    """레거시 파서 로더. registry 파서에 매핑."""
    if version == "latest":
        active = os.environ.get("PARSER_VERSION", "v1.0.0")
        version = active
    parser = get_parser("registry", version)
    return ParserWrapper(parser)


def list_parsers() -> List[str]:
    """레거시: 사용 가능한 파서 버전 목록 (registry 파서)"""
    versions = ["latest"]
    for v in list_versions("registry"):
        versions.append(f"v{v}")
    return versions
