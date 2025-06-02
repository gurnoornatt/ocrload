"""Application configuration settings."""


from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=False, extra="ignore"
    )

    # Application settings
    app_name: str = Field(
        default="OCR & Docs Micro-Service", description="Application name"
    )
    app_version: str = Field(default="0.1.0", description="Application version")
    debug: bool = Field(default=False, description="Debug mode")
    log_level: str = Field(default="info", description="Logging level")

    # Supabase configuration
    supabase_url: str = Field(
        default="https://placeholder.supabase.co", description="Supabase project URL"
    )
    supabase_anon_key: str = Field(
        default="placeholder-anon-key", description="Supabase anonymous key"
    )
    supabase_service_key: str | None = Field(
        default=None, description="Supabase service key for admin operations"
    )

    # OCR API configuration
    DATALAB_API_KEY: str = Field(
        default="placeholder-datalab-key",
        description="Datalab.to API key (also used for Marker feature)",
    )

    # Storage configuration
    aws_region: str = Field(
        default="us-east-1", description="AWS region for S3 operations"
    )
    s3_bucket: str = Field(
        default="raw_docs", description="S3 bucket name for document storage"
    )

    # Redis configuration
    redis_url: str | None = Field(
        default=None, description="Redis URL for event system"
    )
    redis_token: str | None = Field(
        default=None, description="Redis REST token for Upstash authentication"
    )

    # Optional APIs
    openai_api_key: str | None = Field(
        default=None, description="OpenAI API key for fallback processing"
    )

    # Performance settings
    ocr_timeout: int = Field(
        default=30, description="OCR processing timeout in seconds"
    )
    max_file_size: int = Field(
        default=52428800, description="Maximum file size in bytes (50MB)"
    )
    max_workers: int = Field(default=4, description="Maximum number of worker threads")

    # Health check settings
    health_check_timeout: int = Field(
        default=5, description="Health check timeout in seconds"
    )

    @property
    def is_production(self) -> bool:
        """Check if running in production environment."""
        return not self.debug

    def validate_production_config(self) -> bool:
        """Validate that all required production settings are properly configured."""
        placeholders = [
            ("supabase_url", "placeholder.supabase.co"),
            ("supabase_anon_key", "placeholder-anon-key"),
            ("DATALAB_API_KEY", "placeholder-datalab-key"),
        ]

        issues = []
        for field_name, placeholder in placeholders:
            value = getattr(self, field_name)
            if placeholder in value:
                issues.append(f"{field_name} is using placeholder value")

        if issues and self.is_production:
            raise ValueError(
                f"Production deployment with placeholder values: {', '.join(issues)}"
            )
        elif issues:
            import logging

            logger = logging.getLogger(__name__)
            logger.warning(
                f"Development mode with placeholder values: {', '.join(issues)}"
            )

        return len(issues) == 0

    def get_supabase_config(self) -> dict:
        """Get Supabase configuration for client initialization."""
        return {
            "url": self.supabase_url,
            "key": self.supabase_service_key or self.supabase_anon_key,
        }

    def get_redis_config(self) -> dict | None:
        """Get Redis configuration if available."""
        if not self.redis_url:
            return None
        return {"url": self.redis_url}


# Global settings instance
settings = Settings()
