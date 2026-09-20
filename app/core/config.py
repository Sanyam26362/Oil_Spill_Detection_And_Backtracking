# app/config.py
from urllib.parse import quote_plus

from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    PROJECT_NAME: str = "SIH Oil Spill & Vessel Attribution API"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:5173"

    # Database Settings
    POSTGRES_USER: str = ""
    POSTGRES_PASSWORD: str = ""
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = ""

    # G5: Optional full DATABASE_URL override (takes precedence when set).
    DATABASE_URL: str | None = None

    # D4: Connection pool settings (configurable via env).
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 10

    @property
    def async_database_url(self) -> str:
        # G5: Honour explicit DATABASE_URL override first.
        if self.DATABASE_URL:
            return self.DATABASE_URL
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