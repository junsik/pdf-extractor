"""
파서 플러그인 시스템 ↔ 애플리케이션 포트 어댑터

application.ports.parser_service.DocumentParserPort를 구현하여
parsers/ 플러그인 시스템을 유스케이스에서 사용할 수 있게 한다.
"""
from typing import Dict, Any, List, Tuple

from application.ports.parser_service import DocumentParserPort
from parsers import get_parser, detect_document_type, list_document_types, list_versions


class ParserServiceAdapter(DocumentParserPort):
    """파서 플러그인 시스템을 DocumentParserPort로 어댑팅"""

    def parse(self, document_type: str, pdf_buffer: bytes,
              version: str = "latest") -> Dict[str, Any]:
        parser = get_parser(document_type, version)
        result = parser.parse(pdf_buffer)
        return result.data

    def get_parser_version(self, document_type: str,
                            version: str = "latest") -> str:
        parser = get_parser(document_type, version)
        return parser.parser_version()

    def list_document_types(self) -> List[str]:
        return [info.type_id for info in list_document_types()]

    def detect_type(self, pdf_buffer: bytes) -> Tuple[str, float]:
        return detect_document_type(pdf_buffer)

    def mask_for_demo(self, document_type: str, data: Dict[str, Any]) -> Dict[str, Any]:
        parser = get_parser(document_type)
        return parser.mask_for_demo(data)
