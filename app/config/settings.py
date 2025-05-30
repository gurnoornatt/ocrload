"""Application configuration settings."""

from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )

    # Application settings
    app_name: str = Field(default="OCR & Docs Micro-Service", description="Application name")
    app_version: str = Field(default="0.1.0", description="Application version")
    debug: bool = Field(default=False, description="Debug mode")
    log_level: str = Field(default="info", description="Logging level")

    # Supabase configuration
    supabase_url: str = Field(..., description="Supabase project URL")
    supabase_anon_key: str = Field(..., description="Supabase anonymous key")
    supabase_service_key: Optional[str] = Field(default=None, description="Supabase service key for admin operations")

    # OCR API configuration
    DATALAB_API_KEY: str = Field(..., description="Datalab.to API key (also used for Marker feature)")

    # Storage configuration
    aws_region: str = Field(default="us-east-1", description="AWS region for S3 operations")
    s3_bucket: str = Field(default="raw_docs", description="S3 bucket name for document storage")

    # Redis configuration
    redis_url: Optional[str] = Field(default=None, description="Redis URL for event system")
    redis_token: Optional[str] = Field(default=None, description="Redis REST token for Upstash authentication")

    # Optional APIs
    openai_api_key: Optional[str] = Field(default=None, description="OpenAI API key for fallback processing")

    # Performance settings
    ocr_timeout: int = Field(default=30, description="OCR processing timeout in seconds")
    max_file_size: int = Field(default=10485760, description="Maximum file size in bytes (10MB)")
    max_workers: int = Field(default=4, description="Maximum number of worker threads")

    # Health check settings
    health_check_timeout: int = Field(default=5, description="Health check timeout in seconds")

    @property
    def is_production(self) -> bool:
        """Check if running in production environment."""
        return not self.debug

    def get_supabase_config(self) -> dict:
        """Get Supabase configuration for client initialization."""
        return {
            "url": self.supabase_url,
            "key": self.supabase_service_key or self.supabase_anon_key,
        }

    def get_redis_config(self) -> Optional[dict]:
        """Get Redis configuration if available."""
        if not self.redis_url:
            return None
        return {"url": self.redis_url}


# Global settings instance
settings = Settings() 