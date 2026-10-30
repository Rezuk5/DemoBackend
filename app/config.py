from functools import lru_cache
from urllib.parse import urlsplit

from pydantic import Field, HttpUrl, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

COOKIE_NAME = "meetpoint_session"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: SecretStr = SecretStr(
        "postgresql+psycopg://meetpoint:meetpoint@localhost:5432/meetpoint"
    )
    public_base_url: HttpUrl = HttpUrl("http://localhost:8000")
    session_days: int = Field(default=30, ge=1, le=90)

    @field_validator("public_base_url")
    @classmethod
    def require_origin(cls, value: HttpUrl) -> HttpUrl:
        if value.path not in (None, "/") or value.query or value.fragment or value.username:
            raise ValueError("PUBLIC_BASE_URL должен содержать только схему, адрес и порт")
        return value

    @property
    def origin(self) -> str:
        return str(self.public_base_url).rstrip("/")

    @property
    def secure_cookie(self) -> bool:
        return urlsplit(self.origin).scheme == "https"


@lru_cache
def get_settings() -> Settings:
    return Settings()
