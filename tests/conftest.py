from collections.abc import Iterator

import pytest


@pytest.fixture
def clear_settings_cache() -> Iterator[None]:
    from cardinal.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
