"""화면·API 접근 아이디/비밀번호(HTTP Basic) — 환경변수가 모두 있을 때만 켜진다."""
import base64

import pytest
from fastapi.testclient import TestClient

from app.main import app


def basic(user: str, password: str) -> dict[str, str]:
    token = base64.b64encode(f"{user}:{password}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("CHATBOT_BASIC_USER", raising=False)
    monkeypatch.delenv("CHATBOT_BASIC_PASSWORD", raising=False)


def test_open_when_not_configured(client):
    assert client.get("/v1/config").status_code == 200


def test_only_one_value_does_not_enable_it(client, monkeypatch):
    monkeypatch.setenv("CHATBOT_BASIC_USER", "poc")
    assert client.get("/v1/config").status_code == 200


def test_requires_credentials_when_configured(client, monkeypatch):
    monkeypatch.setenv("CHATBOT_BASIC_USER", "poc")
    monkeypatch.setenv("CHATBOT_BASIC_PASSWORD", "s3cret-비밀")
    res = client.get("/v1/config")
    assert res.status_code == 401
    assert res.headers["www-authenticate"].startswith("Basic")


def test_accepts_correct_credentials(client, monkeypatch):
    monkeypatch.setenv("CHATBOT_BASIC_USER", "poc")
    monkeypatch.setenv("CHATBOT_BASIC_PASSWORD", "s3cret-비밀")
    assert client.get("/v1/config", headers=basic("poc", "s3cret-비밀")).status_code == 200


@pytest.mark.parametrize("user,password", [("poc", "wrong"), ("other", "s3cret-비밀"), ("", ""), ("poc", "")])
def test_rejects_wrong_credentials(client, monkeypatch, user, password):
    monkeypatch.setenv("CHATBOT_BASIC_USER", "poc")
    monkeypatch.setenv("CHATBOT_BASIC_PASSWORD", "s3cret-비밀")
    assert client.get("/v1/config", headers=basic(user, password)).status_code == 401


def test_rejects_malformed_header(client, monkeypatch):
    monkeypatch.setenv("CHATBOT_BASIC_USER", "poc")
    monkeypatch.setenv("CHATBOT_BASIC_PASSWORD", "pw")
    assert client.get("/v1/config", headers={"Authorization": "Basic !!!not-base64!!!"}).status_code == 401
    assert client.get("/v1/config", headers={"Authorization": "Bearer abc"}).status_code == 401


def test_health_stays_open_for_container_checks(client, monkeypatch):
    monkeypatch.setenv("CHATBOT_BASIC_USER", "poc")
    monkeypatch.setenv("CHATBOT_BASIC_PASSWORD", "pw")
    assert client.get("/health").status_code == 200


def test_chat_endpoint_is_protected_too(client, monkeypatch):
    monkeypatch.setenv("CHATBOT_BASIC_USER", "poc")
    monkeypatch.setenv("CHATBOT_BASIC_PASSWORD", "pw")
    assert client.post("/v1/chat/messages", json={"text": "주차"}).status_code == 401
