"""헬스 체크 라우터"""
from fastapi import APIRouter
from config import settings

router = APIRouter(tags=["시스템"])


@router.get("/health")
async def health_check():
    return {"status": "healthy", "service": settings.APP_NAME, "version": settings.APP_VERSION}


@router.get("/")
async def root():
    return {"service": settings.APP_NAME, "version": settings.APP_VERSION, "docs": "/docs", "health": "/health"}
