from cardinal.config import get_settings


def test_default_environment(clear_settings_cache: None) -> None:
    settings = get_settings()

    assert settings.environment == "local"


def test_postgres_rw_dsn(clear_settings_cache: None) -> None:
    settings = get_settings()

    assert settings.postgres_rw_dsn.startswith("postgresql+psycopg://")
    assert "@localhost:5432/cardinal" in settings.postgres_rw_dsn


def test_postgres_ro_dsn(clear_settings_cache: None) -> None:
    settings = get_settings()

    assert settings.postgres_ro_dsn.startswith("postgresql+psycopg://")
    assert "@localhost:5432/cardinal" in settings.postgres_ro_dsn


def test_service_urls(clear_settings_cache: None) -> None:
    settings = get_settings()

    assert settings.qdrant_url == "http://localhost:6333"
    assert settings.redis_url == "redis://localhost:6379"
    assert settings.ollama_base_url == "http://localhost:11434"


def test_settings_are_cached(clear_settings_cache: None) -> None:
    first = get_settings()
    second = get_settings()

    assert first is second
