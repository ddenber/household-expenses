from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_SECRET = "dev-insecure-change-me"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    database_url: str = "postgresql+psycopg://hem:hem_dev_pw@localhost:5432/hem"
    redis_url: str = "redis://localhost:6389/0"
    secret_key: str = DEFAULT_SECRET
    cookie_secure: bool = False
    session_hours: int = 12

    storage_backend: str = "local"  # local | s3
    local_storage_dir: str = "./storage"
    s3_endpoint_url: str = "http://localhost:9000"
    s3_public_endpoint_url: str = ""
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_bucket: str = "hem-receipts"
    s3_region: str = "us-east-1"
    signed_url_seconds: int = 300
    public_api_url: str = ""

    max_upload_bytes: int = 15 * 1024 * 1024
    max_pdf_pages: int = 10

    ocr_provider: str = "rapidocr"  # tesseract | rapidocr | azure_document | simulated | none
    azure_di_endpoint: str = ""
    azure_di_key: str = ""
    azure_di_model: str = "prebuilt-receipt"  # or prebuilt-invoice
    ocr_inline: bool = False
    ocr_confidence_threshold: float = 0.8

    login_rate_limit_per_min: int = 10
    max_failed_logins: int = 5
    lockout_minutes: int = 15
    rate_limit_enabled: bool = True


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    if s.app_env == "production" and s.secret_key == DEFAULT_SECRET:
        raise RuntimeError("SECRET_KEY must be set in production")
    if s.app_env == "production" and not s.cookie_secure:
        raise RuntimeError("COOKIE_SECURE must be true in production")
    return s
