"""
등기부등본 PDF 파싱 서비스 설정
"""
import os
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """애플리케이션 설정"""
    
    # 앱 기본 설정
    APP_NAME: str = "등기부등본 PDF 파싱 서비스"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True
    
    # 서버 설정
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    
    # 데이터베이스 설정 (환경 변수와 충돌 방지를 위해 이름 변경)
    DB_URL: str = "sqlite+aiosqlite:///./data/registry.db"
    
    # JWT 설정
    SECRET_KEY: str = "your-super-secret-key-change-in-production-32chars"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24시간
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7  # 7일
    
    # Toss Payments 설정
    TOSS_CLIENT_KEY: str = "test_ck_Ba5PzR0Arnx65d0PGGOk3vmYnNeD"
    TOSS_SECRET_KEY: str = "test_sk_eqRGgYO1r5M1naPvQZdarQnN2Eya"
    TOSS_API_URL: str = "https://api.tosspayments.com/v1"
    
    # Webhook 설정
    WEBHOOK_TIMEOUT: int = 30  # 초
    WEBHOOK_RETRY_COUNT: int = 3
    WEBHOOK_SECRET: str = "webhook-secret-key-change-in-production"
    
    # 파일 업로드 설정
    MAX_FILE_SIZE: int = 10 * 1024 * 1024  # 10MB
    ALLOWED_EXTENSIONS: list = [".pdf"]
    UPLOAD_DIR: str = "./uploads"
    
    # 요금제 설정 (원)
    PRICING: dict = {
        "free": {
            "name": "무료",
            "price": 0,
            "credits": 3,  # 월 3회
            "features": ["기본 파싱", "데모 결과", "Webhook 미지원"]
        },
        "basic": {
            "name": "베이직",
            "price": 9900,
            "credits": 10,  # 월 10회
            "features": ["전체 파싱", "상세 결과", "Webhook 지원", "API 액세스"]
        },
        "pro": {
            "name": "프로",
            "price": 29900,
            "credits": -1,  # 무제한
            "features": ["무제한 파싱", "우선 처리", "Webhook 지원", "API 액세스", "전담 지원"]
        }
    }
    
    # CORS 설정
    CORS_ORIGINS: list = [
        "http://localhost:3009",
        "http://127.0.0.1:3009",
        "https://registry-parser.com"
    ]
    
    # 로깅 설정
    LOG_LEVEL: str = "DEBUG"
    LOG_FILE: str = "./logs/app.log"
    
    class Config:
        env_file = ".env.backend"  # 백엔드 전용 환경 변수 파일
        case_sensitive = True
        # 부모 디렉토리의 .env 파일 무시
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    """설정 싱글톤 반환"""
    return Settings()


# 설정 인스턴스
settings = get_settings()
