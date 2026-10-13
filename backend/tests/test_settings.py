"""LLM 설정은 환경변수로만 받는다 — 주소·모델이 없으면 LLM 분류를 끈다."""
import pytest

from app.features.chat.settings import load_settings

VARS = ["LLM_BASE_URL", "LLM_MODEL", "LLM_FALLBACK_BASE_URL", "LLM_FALLBACK_MODEL", "LLM_ENABLED", "LLM_TIMEOUT_SECONDS"]


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for name in VARS:
        monkeypatch.delenv(name, raising=False)


def test_without_any_setting_llm_is_disabled():
    s = load_settings()
    assert s.enabled is False
    assert s.endpoints == ()


def test_primary_only(monkeypatch):
    monkeypatch.setenv("LLM_BASE_URL", "http://llm.test:8000/v1/")
    monkeypatch.setenv("LLM_MODEL", "model-a")
    s = load_settings()
    assert s.enabled is True
    assert [(e.base_url, e.model) for e in s.endpoints] == [("http://llm.test:8000/v1", "model-a")]


def test_fallback_is_second(monkeypatch):
    monkeypatch.setenv("LLM_BASE_URL", "http://a.test/v1")
    monkeypatch.setenv("LLM_MODEL", "model-a")
    monkeypatch.setenv("LLM_FALLBACK_BASE_URL", "http://b.test/v1")
    monkeypatch.setenv("LLM_FALLBACK_MODEL", "model-b")
    assert [e.model for e in load_settings().endpoints] == ["model-a", "model-b"]


def test_url_without_model_is_ignored(monkeypatch):
    monkeypatch.setenv("LLM_BASE_URL", "http://a.test/v1")
    assert load_settings().enabled is False


@pytest.mark.parametrize("value", ["0", "false", "OFF"])
def test_can_be_switched_off(monkeypatch, value):
    monkeypatch.setenv("LLM_BASE_URL", "http://a.test/v1")
    monkeypatch.setenv("LLM_MODEL", "model-a")
    monkeypatch.setenv("LLM_ENABLED", value)
    s = load_settings()
    assert s.enabled is False
    assert len(s.endpoints) == 1
