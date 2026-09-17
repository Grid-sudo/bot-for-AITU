from __future__ import annotations

from app.config import Settings


def _settings(admin_ids_raw: str) -> Settings:
    return Settings(
        BOT_TOKEN="123:test-token",
        DATABASE_URL="sqlite+aiosqlite:///:memory:",
        ADMIN_IDS=admin_ids_raw,
    )


def test_admin_ids_parsed_from_csv():
    settings = _settings("111, 222,333")
    assert settings.admin_ids == {111, 222, 333}


def test_is_admin_true_for_listed_id():
    settings = _settings("111,222")
    assert settings.is_admin(111) is True


def test_is_admin_false_for_unlisted_id():
    settings = _settings("111,222")
    assert settings.is_admin(999) is False


def test_malformed_admin_id_is_ignored_not_fatal():
    settings = _settings("111,not-a-number,222")
    assert settings.admin_ids == {111, 222}


def test_empty_admin_ids_means_nobody_is_admin():
    settings = _settings("")
    assert settings.admin_ids == set()
    assert settings.is_admin(111) is False
