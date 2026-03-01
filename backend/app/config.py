"""Application configuration via Pydantic Settings.

Centralizes all environment variables with validation. Railway passes
env vars as strings, so list fields use a flexible validator that
accepts both comma-separated strings and actual lists.
"""

from typing import Union

from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Supabase
    supabase_url: str
    supabase_service_role_key: str
    supabase_jwt_secret: str

    # LLM providers
    deepinfra_api_key: str
    fireworks_api_key: str = ""
    anthropic_api_key: str

    # Stripe
    stripe_secret_key: str
    stripe_webhook_secret: str
    stripe_writer_price_id: str
    stripe_author_price_id: str

    # Application
    frontend_url: str = "https://bubwriter.com"
    allowed_origins: list[str] = [
        "https://bubwriter.com",
        "https://www.bubwriter.com",
        "https://bubwriter.vercel.app",
        "http://localhost:3000",
    ]

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def parse_allowed_origins(cls, v: Union[str, list[str]]) -> list[str]:
        """Accept comma-separated string or list for Railway compatibility."""
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
    }


settings = Settings()  # type: ignore[call-arg]
