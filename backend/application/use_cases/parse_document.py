"""PDF 문서 파싱 유스케이스"""
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Dict, Any

from domain.exceptions import InsufficientCreditsError, DailyLimitExceededError
from application.ports.user_repository import UserRepository
from application.ports.parse_record_repository import ParseRecordRepository
from application.ports.product_repository import ProductRepository
from application.ports.parser_service import DocumentParserPort


@dataclass
class ParseDocumentInput:
    user_id: int
    document_type: Optional[str]  # None이면 자동 감지
    file_name: str
    file_content: bytes
    demo_mode: bool = False
    webhook_url: Optional[str] = None
    parser_version: str = "latest"


@dataclass
class ParseDocumentOutput:
    success: bool
    request_id: str
    status: str = "completed"
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    remaining_credits: int = 0
    is_demo: bool = False
    document_type: Optional[str] = None
    parser_version: Optional[str] = None


class ParseDocumentUseCase:
    """PDF 파싱 유스케이스 — main.py의 parse_pdf 비즈니스 로직 추출"""

    def __init__(
        self,
        user_repo: UserRepository,
        parse_record_repo: ParseRecordRepository,
        product_repo: ProductRepository,
        parser_service: DocumentParserPort,
        pricing_config: dict,
    ):
        self._user_repo = user_repo
        self._parse_record_repo = parse_record_repo
        self._product_repo = product_repo
        self._parser = parser_service
        self._pricing = pricing_config

    async def execute(self, input: ParseDocumentInput) -> ParseDocumentOutput:
        request_id = str(uuid.uuid4())

        # 1. 사용자 조회
        user = await self._user_repo.get_by_id(input.user_id)
        if user is None:
            return ParseDocumentOutput(success=False, request_id=request_id,
                                       status="failed", error="사용자를 찾을 수 없습니다.")

        # 2. 문서 타입 결정
        document_type = input.document_type
        if document_type is None:
            try:
                document_type, _ = self._parser.detect_type(input.file_content)
            except ValueError:
                document_type = "registry"

        # 3. 상품 확인
        credit_cost = 1
        product = await self._product_repo.get_by_id(document_type)
        if product:
            product.ensure_enabled()
            credit_cost = product.credit_cost

        # 4. 크레딧 확인
        if not user.can_parse():
            raise InsufficientCreditsError()

        # 5. 일일 한도 확인
        plan_key = user.plan
        daily_limit = self._pricing.get(plan_key, {}).get("daily_limit", 3)
        if daily_limit != -1:
            today_count = await self._parse_record_repo.count_today(user.id)
            if today_count >= daily_limit:
                raise DailyLimitExceededError(daily_limit)

        # 6. 파싱 기록 생성
        record_id = await self._parse_record_repo.create(
            user_id=user.id, file_name=input.file_name,
            file_size=len(input.file_content), document_type=document_type,
        )

        try:
            # 7. PDF 파싱
            start_time = datetime.utcnow()
            parsed_data = self._parser.parse(document_type, input.file_content, input.parser_version)
            processing_time = (datetime.utcnow() - start_time).total_seconds()
            parser_version = self._parser.get_parser_version(document_type, input.parser_version)

            # 8. 데모 마스킹
            response_data = parsed_data
            if input.demo_mode:
                response_data = self._parser.mask_for_demo(document_type, parsed_data)

            # 9. 기록 완료
            await self._parse_record_repo.update_completed(record_id, parsed_data, processing_time, parser_version)

            # 10. 크레딧 차감
            user.deduct_credit(credit_cost)
            await self._user_repo.update_credits(user.id, user.credits, user.credits_used)

            return ParseDocumentOutput(
                success=True, request_id=request_id, status="completed",
                data=response_data, remaining_credits=user.credits,
                is_demo=input.demo_mode, document_type=document_type, parser_version=parser_version,
            )

        except Exception as e:
            await self._parse_record_repo.update_failed(record_id, str(e))
            return ParseDocumentOutput(
                success=False, request_id=request_id, status="failed",
                error=str(e), is_demo=input.demo_mode,
                remaining_credits=user.credits if user else 0,
            )
