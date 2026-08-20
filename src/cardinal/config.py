from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: str = "local"

    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "cardinal"
    postgres_user: str
    postgres_password: str

    warehouse_ro_host: str = "localhost"
    warehouse_ro_port: int = 5432
    warehouse_ro_db: str = "cardinal"
    warehouse_ro_user: str
    warehouse_ro_password: str

    qdrant_url: str = "http://localhost:6333"
    redis_url: str = "redis://localhost:6379"
    ollama_base_url: str = "http://localhost:11434"

    @property
    def postgres_rw_dsn(self) -> str:
        return (
            f"postgresql+psycopg://{self.postgres_user}:"
            f"{self.postgres_password}@{self.postgres_host}:"
            f"{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def postgres_ro_dsn(self) -> str:
        return (
            f"postgresql+psycopg://{self.warehouse_ro_user}:"
            f"{self.warehouse_ro_password}@{self.warehouse_ro_host}:"
            f"{self.warehouse_ro_port}/{self.warehouse_ro_db}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
