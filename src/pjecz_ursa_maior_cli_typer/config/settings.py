"""
Config Settings
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Settings"""

    DB_USER: str = "username"
    DB_PASS: str = "password"
    DB_HOST: str = "localhost"
    DB_PORT: int = 5432
    DB_NAME: str = "database"
    LIMIT: int = 20
    SALT: str = "some_random_salt"
    SQLALCHEMY_DATABASE_URI: str = f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    TIMEOUT: int = 30
    TZ: str = "America/Mexico_City"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    def build_database_uri(self) -> str:
        """Construye la URI cuando no está provista directamente."""
        if self.SQLALCHEMY_DATABASE_URI:
            return self.SQLALCHEMY_DATABASE_URI

        if not (self.DB_USER and self.DB_PASS and self.DB_NAME):
            return "postgresql+psycopg2://localhost:5432/postgres"

        return (
            f"postgresql+psycopg2://{self.DB_USER}:{self.DB_PASS}"
            f"@{self.DB_HOST or '127.0.0.1'}:{self.DB_PORT or '5432'}/{self.DB_NAME}"
        )

    @property
    def database_uri(self) -> str:
        """URI de la base de datos PostgreSQL."""
        return self.build_database_uri()


@lru_cache
def get_settings() -> Settings:
    """Get settings"""
    return Settings()
