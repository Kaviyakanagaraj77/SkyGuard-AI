"""
SkyGuard AI v2 - Centralized Configuration Management (Phase 5)
----------------------------------------------------------------
Provides environment-driven configuration for database, JWT authentication,
CORS origins, logging levels, application environment, and deployment settings.
"""

import os
from typing import List


class Settings:
    # Application & Environment Tiers
    APP_NAME: str = "SkyGuard AI"
    APP_VERSION: str = "2.0"
    APP_ENV: str = os.environ.get("APP_ENV", "development").lower()
    LOG_LEVEL: str = os.environ.get("LOG_LEVEL", "INFO").upper()

    # Database Settings
    DATABASE_URL: str = os.environ.get("DATABASE_URL", "")
    DB_POOL_SIZE: int = int(os.environ.get("DB_POOL_SIZE", "5"))
    DB_MAX_OVERFLOW: int = int(os.environ.get("DB_MAX_OVERFLOW", "10"))

    # Security & JWT Token Settings
    _raw_jwt_secret = os.environ.get("JWT_SECRET")
    if not _raw_jwt_secret or _raw_jwt_secret == "CHANGE_ME_TO_A_RANDOM_32_BYTE_SECRET":
        JWT_SECRET: str = "skyguard_sih_2026_production_secret_key_32bytes_long"
    else:
        JWT_SECRET: str = _raw_jwt_secret

    JWT_ALGORITHM: str = os.environ.get("JWT_ALGORITHM", "HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.environ.get("ACCESS_TOKEN_EXPIRE_MINUTES", "480"))

    # CORS Allowed Origins
    _raw_cors = os.environ.get("CORS_ORIGINS", "")
    if _raw_cors:
        CORS_ORIGINS: List[str] = [o.strip() for o in _raw_cors.split(",") if o.strip()]
    else:
        # Default Vercel production frontend + local dev URLs
        CORS_ORIGINS: List[str] = [
            "https://sky-guard-ai-seven.vercel.app",
            "http://127.0.0.1:8080",
            "http://localhost:8080",
            "http://127.0.0.1:8000",
            "http://localhost:8000",
            "*"
        ]

    # Rate Limiting & Abuse Protection
    RATE_LIMIT_LOGIN_MAX_ATTEMPTS: int = int(os.environ.get("RATE_LIMIT_LOGIN_MAX_ATTEMPTS", "10"))
    RATE_LIMIT_WINDOW_SECONDS: int = int(os.environ.get("RATE_LIMIT_WINDOW_SECONDS", "60"))

    def validate_production_config(self) -> List[str]:
        """Validates configuration safety for production deployment."""
        warnings = []
        if self.APP_ENV == "production":
            if self.JWT_SECRET == "skyguard_sih_2026_production_secret_key_32bytes_long":
                warnings.append("JWT_SECRET is using default demo secret. Provide a custom JWT_SECRET in production.")
            if "*" in self.CORS_ORIGINS:
                warnings.append("CORS_ORIGINS contains wildcard '*' in production. Specify exact frontend origin URLs.")
        return warnings


settings = Settings()
