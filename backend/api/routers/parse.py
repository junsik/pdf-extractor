"""PDF 파싱 라우터"""
import json
import uuid
from datetime import datetime, date
from typing import Optional

from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException, status, BackgroundTasks, Query
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from config import settings
from infrastructure.persistence.database import get_session
from infrastructure.persistence.models.parse_record import ParseRecord
from infrastructure.persistence.models.user import User
from domain.enums import ParseStatus
from api.schemas.parse import ParseResponse, ParseHistoryResponse, ParseHistoryItem
from api.dependencies import get_current_active_user
from parsers import get_parser
from infrastructure.webhook.sender import webhook_sender

router = APIRouter(prefix="/api/parse", tags=["PDF 파싱"])


@router.post("", response_model=ParseResponse)
async def parse_pdf(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    demo_mode: bool = Form(False),
    webhook_url: Optional[str] = Form(None),
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_session)
):
    """PDF 파싱"""
    request_id = str(uuid.uuid4())

    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="PDF 파일만 업로드 가능합니다.")

    content = await file.read()
    if len(content) > settings.MAX_FILE_SIZE:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"파일 크기는 {settings.MAX_FILE_SIZE // 1024 // 1024}MB 이하여야 합니다.")

    remaining_credits = current_user.credits
    if current_user.credits != -1 and current_user.credits <= 0:
        raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED,
                            detail="크레딧이 부족합니다. 요금제를 업그레이드 해주세요.")

    plan_key = current_user.plan.value if current_user.plan else "free"
    daily_limit = settings.PRICING.get(plan_key, {}).get("daily_limit", 3)
    if daily_limit != -1:
        today_start = datetime.combine(date.today(), datetime.min.time())
        today_count_result = await session.execute(
            select(func.count(ParseRecord.id)).where(
                ParseRecord.user_id == current_user.id, ParseRecord.created_at >= today_start))
        today_count = today_count_result.scalar() or 0
        if today_count >= daily_limit:
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                                detail=f"일일 파싱 한도({daily_limit}회)를 초과했습니다.")

    parse_record = ParseRecord(user_id=current_user.id, file_name=file.filename,
                               file_size=len(content), status=ParseStatus.PROCESSING)
    session.add(parse_record)
    await session.flush()

    try:
        start_time = datetime.utcnow()
        parser = get_parser("registry")
        result = parser.parse(content)
        parsed_data = result.data
        processing_time = (datetime.utcnow() - start_time).total_seconds()

        response_data = parser.mask_for_demo(parsed_data) if demo_mode else parsed_data

        parse_record.status = ParseStatus.COMPLETED
        parse_record.unique_number = parsed_data.get("unique_number", "")
        parse_record.property_type = parsed_data.get("property_type", "")
        parse_record.property_address = parsed_data.get("property_address", "")
        parse_record.result_json = json.dumps(parsed_data, ensure_ascii=False)
        parse_record.section_a_count = len(parsed_data.get("section_a", []))
        parse_record.section_b_count = len(parsed_data.get("section_b", []))
        parse_record.completed_at = datetime.utcnow()
        parse_record.processing_time = processing_time

        if current_user.credits != -1:
            current_user.credits -= 1
            remaining_credits = current_user.credits
        current_user.credits_used += 1

        webhook_url_to_use = webhook_url or current_user.webhook_url
        if webhook_url_to_use and current_user.webhook_enabled:
            background_tasks.add_task(webhook_sender.send_parsing_completed,
                                      webhook_url_to_use, request_id, response_data,
                                      f"/api/parse/{parse_record.id}", current_user.webhook_secret)

        logger.info(f"PDF 파싱 완료: {file.filename} - {parsed_data.get('unique_number', 'N/A')}")
        return ParseResponse(success=True, request_id=request_id, status="completed",
                             data=response_data, is_demo=demo_mode, remaining_credits=remaining_credits)

    except Exception as e:
        logger.error(f"PDF 파싱 실패: {str(e)}")
        parse_record.status = ParseStatus.FAILED
        parse_record.error_message = str(e)

        webhook_url_to_use = webhook_url or current_user.webhook_url
        if webhook_url_to_use and current_user.webhook_enabled:
            background_tasks.add_task(webhook_sender.send_parsing_failed,
                                      webhook_url_to_use, request_id, str(e), current_user.webhook_secret)

        return ParseResponse(success=False, request_id=request_id, status="failed",
                             error=str(e), is_demo=demo_mode, remaining_credits=remaining_credits)


@router.get("/history", response_model=ParseHistoryResponse)
async def get_parse_history(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_session)
):
    count_result = await session.execute(
        select(func.count()).select_from(ParseRecord).where(ParseRecord.user_id == current_user.id))
    total = count_result.scalar()

    result = await session.execute(
        select(ParseRecord).where(ParseRecord.user_id == current_user.id)
        .order_by(desc(ParseRecord.created_at)).offset((page - 1) * page_size).limit(page_size))
    records = result.scalars().all()

    items = [ParseHistoryItem(id=r.id, file_name=r.file_name, status=r.status.value,
                               unique_number=r.unique_number, property_address=r.property_address,
                               section_a_count=r.section_a_count, section_b_count=r.section_b_count,
                               created_at=r.created_at, completed_at=r.completed_at,
                               processing_time=r.processing_time) for r in records]

    return ParseHistoryResponse(success=True, items=items, total=total, page=page, page_size=page_size)
