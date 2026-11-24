import os

import pytest

from app.config_store import SecretConfigStore


def test_secret_config_is_saved_without_being_returned(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    path = tmp_path / ".env"
    path.write_text("LANGUAGE=chinese\nOPENAI_API_KEY=\n", encoding="utf-8")
    store = SecretConfigStore(path)
    status = store.save({"OPENAI_API_KEY": "sk-example-123456789", "TAVILY_API_KEY": "tvly-example-123456789"})
    assert status == {"OPENAI_API_KEY": True, "TAVILY_API_KEY": True}
    assert "sk-example-123456789" in path.read_text(encoding="utf-8")
    assert path.stat().st_mode & 0o777 == 0o600


def test_secret_config_rejects_spaces(tmp_path):
    store = SecretConfigStore(tmp_path / ".env")
    with pytest.raises(ValueError):
        store.save({"OPENAI_API_KEY": "not a valid key with spaces"})


def test_key_round_trips_dotenv_special_characters(tmp_path, monkeypatch):
    from dotenv import dotenv_values
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    value = "sk-special#quote'value123456"
    path = tmp_path / ".env"
    SecretConfigStore(path).save({"OPENAI_API_KEY": value})
    assert dotenv_values(path)["OPENAI_API_KEY"] == value
