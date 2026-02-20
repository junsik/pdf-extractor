"""
등기부등본 (Property Registry) 파서 플러그인

부동산 등기부등본 PDF를 파싱하여 표제부, 갑구, 을구 데이터를 구조화한다.
토지 / 건물 / 집합건물 3가지 타입을 내부적으로 자동 감지하여 처리한다.
"""
from parsers.registry.v1_0_0 import RegistryParserV1

PARSER_CLASSES = [RegistryParserV1]
