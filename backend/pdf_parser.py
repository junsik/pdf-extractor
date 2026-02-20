"""
등기부등본 PDF 파서 — 래퍼 모듈

실제 파서 구현은 parsers/ 패키지에 버전별로 관리된다.
이 파일은 현재 활성 버전을 로드하여 서비스(main.py)에 노출한다.

버전 전환:
  ACTIVE_VERSION을 변경하면 서비스가 사용하는 파서가 바뀐다.
  예: "v1.0.0" → "v1.1.0"

인터페이스:
  - PARSER_VERSION: str
  - parse_registry_pdf(pdf_buffer: bytes) -> Dict[str, Any]
  - mask_for_demo(data: Dict) -> Dict  (서비스 전용, 파서 인터페이스 아님)
"""
import os
import copy
from typing import Dict, Any

from parsers import load_parser

# ==================== 활성 파서 버전 ====================
# 이 값을 바꾸면 서비스가 사용하는 파서가 전환된다.
# 환경변수 PARSER_VERSION으로도 오버라이드 가능.

ACTIVE_VERSION = os.environ.get("PARSER_VERSION", "v1.0.0")

_parser = load_parser(ACTIVE_VERSION)

PARSER_VERSION = _parser.PARSER_VERSION
parse_registry_pdf = _parser.parse_registry_pdf


# ==================== 서비스 전용 유틸리티 ====================

def mask_for_demo(data: Dict[str, Any]) -> Dict[str, Any]:
    """데모 버전용 데이터 마스킹"""
    masked = copy.deepcopy(data)

    # 표제부 면적은 첫 층만
    if 'title_info' in masked and 'areas' in masked['title_info']:
        masked['title_info']['areas'] = masked['title_info']['areas'][:1]

    # 갑구 첫 항목만, 개인정보 마스킹
    if 'section_a' in masked and masked['section_a']:
        first_entry = masked['section_a'][0]
        if first_entry.get('owner'):
            owner = first_entry['owner']
            if owner.get('name'):
                name = owner['name']
                owner['name'] = (
                    name[0] + '*' * (len(name) - 2) + name[-1]
                    if len(name) > 2 else name[0] + '*'
                )
            owner['resident_number'] = '******-*******'
            owner['address'] = '***' if owner.get('address') else None
        masked['section_a'] = [first_entry]

    # 을구 첫 항목만, 금액 숨김
    if 'section_b' in masked and masked['section_b']:
        first_entry = masked['section_b'][0]
        first_entry['max_claim_amount'] = None
        first_entry['deposit_amount'] = None
        first_entry['mortgagee'] = None
        first_entry['lessee'] = None
        masked['section_b'] = [first_entry]

    return masked
