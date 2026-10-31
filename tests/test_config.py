import pytest

from app.config import load_settings, parse_user_ids


def test_parses_comma_separated_ids():
    assert parse_user_ids("123, 456,789") == {123, 456, 789}


def test_empty_means_nobody():
    assert parse_user_ids("") == frozenset()
    assert parse_user_ids(" , ") == frozenset()


def test_rejects_non_numeric():
    with pytest.raises(ValueError):
        parse_user_ids("123,@kaamesh")


def test_load_settings_requires_anthropic_key(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:fake")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(SystemExit):
        load_settings()


def test_load_settings_reads_all_values(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:fake")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-fake")
    monkeypatch.setenv("ALLOWED_USER_IDS", "42")
    settings = load_settings()
    assert settings.anthropic_api_key == "sk-ant-fake"
    assert settings.allowed_user_ids == {42}
