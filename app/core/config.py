# app/config.py
from urllib.parse import quote_plus, urlparse

from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    PROJECT_NAME: str = "SIH Oil Spill & Vessel Attribution API"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:5173,*"

    # Database Settings
    POSTGRES_USER: str = ""
    POSTGRES_PASSWORD: str = ""
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = ""

    # G5: Optional full DATABASE_URL or NEON_URL override (takes precedence when set).
    DATABASE_URL: str | None = None
    NEON_URL: str | None = None

    # D4: Connection pool settings (configurable via env).
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 10

    @property
    def async_database_url(self) -> str:
        # Check NEON_URL first, then explicit DATABASE_URL
        raw_url = self.NEON_URL or self.DATABASE_URL
        if raw_url:
            parsed = urlparse(raw_url)
            # Use postgresql+asyncpg driver and strip query params (sslmode, channel_binding)
            return f"postgresql+asyncpg://{parsed.netloc}{parsed.path}"
        # G5: URL-encode credentials so passwords containing @, : or /
        # produce a valid DSN instead of a parse error.
        user = quote_plus(self.POSTGRES_USER)
        password = quote_plus(self.POSTGRES_PASSWORD)
        return (
            f"postgresql+asyncpg://{user}:{password}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True, extra="ignore")

settings = Settings()