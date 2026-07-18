import pytest

from app.config import clear_settings_cache
from app.services.limits import reset_limit_state


@pytest.fixture(autouse=True)
def _reset_process_limits(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "10000")
    # Force open (unkeyed) default so a developer .env API_KEY cannot break tests.
    monkeypatch.setenv("API_KEY", "")
    clear_settings_cache()
    reset_limit_state()
    yield
    clear_settings_cache()
    reset_limit_state()
