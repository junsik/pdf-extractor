"""
등기부등본 PDF 파싱 서비스 — FastAPI App Factory

모든 라우트 핸들러는 api/routers/로 분리되었다.
이 파일은 앱 생성, 미들웨어, lifespan만 담당한다.
"""
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from config import settings
from infrastructure.persistence.database import init_db

# 로깅 설정
os.makedirs("./logs", exist_ok=True)
logger.add(
    settings.LOG_FILE,
    rotation="10 MB",
    retention="30 days",
    level=settings.LOG_LEVEL
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """애플리케이션 수명 주기 관리"""
    logger.info("서비스 시작...")
    await init_db()
    logger.info("데이터베이스 초기화 완료")
    yield
    logger.info("서비스 종료...")


# FastAPI 앱 생성
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="등기부등본 PDF 파싱 서비스 - 표제부, 갑구, 을구 자동 분석",
    lifespan=lifespan
)

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==================== 라우터 등록 ====================
from api.routers import health, auth, parse, payment, user, products

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(parse.router)
app.include_router(payment.router)
app.include_router(user.router)
app.include_router(products.router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=settings.HOST, port=settings.PORT, reload=settings.DEBUG)
