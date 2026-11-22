"""The cloud server gets the Firebase key from the FIREBASE_KEY_JSON secret, never logged."""
import logging

from app.services import firebase


def test_bad_key_json_is_rejected_without_logging_it(monkeypatch, caplog):
    monkeypatch.setenv("FIREBASE_KEY_JSON", "not-json-secret-value")
    with caplog.at_level(logging.ERROR):
        assert firebase._credentials() is None
    assert "FIREBASE_KEY_JSON" in caplog.text
    assert "not-json-secret-value" not in caplog.text


def test_no_env_and_no_file_means_memory_only(monkeypatch, tmp_path):
    monkeypatch.delenv("FIREBASE_KEY_JSON", raising=False)
    monkeypatch.setattr(firebase, "FIREBASE_KEY_PATH", tmp_path / "missing.json")
    assert firebase._credentials() is None
