"""POST /v1/chat/messages — LLM 서버는 httpx MockTransport 로 대체한다 (사내 서버에 요청을 보내지 않는다)."""
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.features.chat.router import get_classifier, get_settings
from app.features.chat.service import MAX_INTENTS, IntentClassifier, LlmBadResponse, normalize
from app.features.chat.settings import LlmEndpoint, LlmSettings
from app.main import app

PRIMARY = LlmEndpoint("http://primary.test/v1", "gemma-test")
FALLBACK = LlmEndpoint("http://fallback.test/v1", "Qwen3-test")


def llm_reply(*pairs: tuple[str, str]) -> dict:
    content = json.dumps({"intents": [{"intent": i, "topic": t} for i, t in pairs]})
    return {"choices": [{"message": {"content": content}}]}


def make_client(handler, settings: LlmSettings | None = None) -> TestClient:
    settings = settings or LlmSettings(enabled=True, endpoints=(PRIMARY, FALLBACK), timeout_seconds=2)
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_classifier] = lambda: IntentClassifier(settings, http)
    return TestClient(app)


@pytest.fixture(autouse=True)
def _reset_overrides():
    yield
    app.dependency_overrides.clear()


# ── normalize: LLM 응답 검증 ───────────────────────────────────────────

def test_normalize_single_intent_with_topic():
    out = normalize('{"intents": [{"intent": "info.directions", "topic": "bus"}]}')
    assert [(o.intent, o.label, o.topic) for o in out] == [("info.directions", "오시는 길", "bus")]


def test_normalize_drops_topic_for_intents_that_do_not_use_it():
    out = normalize('{"intents": [{"intent": "faq.parking", "topic": "car"}]}')
    assert out[0].topic is None


def test_normalize_keeps_order_dedupes_and_caps_at_three():
    pairs = [("faq.parking", "none"), ("faq.hours", "none"), ("faq.parking", "none"),
             ("doctor.search", "none"), ("info.health", "none")]
    out = normalize(json.dumps({"intents": [{"intent": i, "topic": t} for i, t in pairs]}))
    assert [o.intent for o in out] == ["faq.parking", "faq.hours", "doctor.search"]
    assert len(out) <= MAX_INTENTS


def test_normalize_emergency_wins_over_everything():
    out = normalize(json.dumps({"intents": [{"intent": "faq.parking", "topic": "none"},
                                            {"intent": "emergency", "topic": "none"}]}))
    assert [o.intent for o in out] == ["emergency"]


def test_normalize_drops_unknown_when_other_intents_exist():
    out = normalize(json.dumps({"intents": [{"intent": "unknown", "topic": "none"},
                                            {"intent": "faq.hours", "topic": "none"}]}))
    assert [o.intent for o in out] == ["faq.hours"]


def test_normalize_accepts_json_in_code_fence():
    out = normalize('```json\n{"intents": [{"intent": "faq.hours", "topic": "none"}]}\n```')
    assert out[0].intent == "faq.hours"


@pytest.mark.parametrize("content", ["", "안녕하세요", "{}", '{"intents": []}', '{"intents": [{"intent": "nope", "topic": "none"}]}',
                                     '{"intents": "faq.hours"}'])
def test_normalize_rejects_unusable_content(content):
    with pytest.raises(LlmBadResponse):
        normalize(content)


# ── 엔드포인트 ──────────────────────────────────────────────────────────

def test_returns_intents_in_spoken_order():
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert request.url.host == "primary.test"
        assert body["response_format"]["type"] == "json_schema"
        assert body["temperature"] == 0
        assert "chat_template_kwargs" not in body  # Qwen 이 아니면 보내지 않는다
        return httpx.Response(200, json=llm_reply(("faq.parking", "none"), ("info.directions", "subway")))

    res = make_client(handler).post("/v1/chat/messages", json={"text": "주차 되나요? 그리고 지하철로 가는 방법도"})
    assert res.status_code == 200
    assert res.json() == {"intents": [
        {"intent": "faq.parking", "label": "주차 안내", "topic": None},
        {"intent": "info.directions", "label": "오시는 길", "topic": "subway"},
    ]}


def test_falls_back_to_second_server_and_disables_thinking_for_qwen():
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.host)
        if request.url.host == "primary.test":
            return httpx.Response(500, text="boom")
        assert json.loads(request.content)["chat_template_kwargs"] == {"enable_thinking": False}
        return httpx.Response(200, json=llm_reply(("faq.hours", "none")))

    res = make_client(handler).post("/v1/chat/messages", json={"text": "몇 시까지 해요"})
    assert res.status_code == 200
    assert seen == ["primary.test", "fallback.test"]
    assert res.json()["intents"][0]["intent"] == "faq.hours"


def test_bad_format_from_first_server_also_tries_next():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "primary.test":
            return httpx.Response(200, json={"choices": [{"message": {"content": "죄송합니다"}}]})
        return httpx.Response(200, json=llm_reply(("faq.parking", "none")))

    res = make_client(handler).post("/v1/chat/messages", json={"text": "주차"})
    assert res.status_code == 200
    assert res.json()["intents"][0]["intent"] == "faq.parking"


def test_sends_api_key_only_when_configured():
    seen: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers.get("authorization"))
        return httpx.Response(200, json=llm_reply(("faq.hours", "none")))

    with_key = LlmSettings(enabled=True, endpoints=(PRIMARY,), timeout_seconds=2, api_key="k-test")
    make_client(handler, with_key).post("/v1/chat/messages", json={"text": "몇 시까지"})
    make_client(handler).post("/v1/chat/messages", json={"text": "몇 시까지"})
    assert seen == ["Bearer k-test", None]


def test_503_when_every_server_fails():
    res = make_client(lambda request: httpx.Response(503, text="down")).post("/v1/chat/messages", json={"text": "주차"})
    assert res.status_code == 503
    assert res.json()["detail"] == "llm_unavailable"


def test_503_when_connection_fails():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route", request=request)

    res = make_client(handler).post("/v1/chat/messages", json={"text": "주차"})
    assert res.status_code == 503


def test_503_when_disabled_without_calling_llm():
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("LLM 을 호출하면 안 됩니다")

    settings = LlmSettings(enabled=False, endpoints=(PRIMARY,), timeout_seconds=2)
    res = make_client(handler, settings).post("/v1/chat/messages", json={"text": "주차"})
    assert res.status_code == 503
    assert res.json()["detail"] == "llm_disabled"


@pytest.mark.parametrize("payload", [{}, {"text": ""}, {"text": "가" * 301}])
def test_rejects_invalid_input(payload):
    res = make_client(lambda request: httpx.Response(200, json=llm_reply(("faq.hours", "none")))).post(
        "/v1/chat/messages", json=payload)
    assert res.status_code == 422


def test_question_text_is_not_logged(caplog):
    caplog.set_level("DEBUG")
    secret = "배가 너무 아프고 어제부터 열이 납니다"
    make_client(lambda request: httpx.Response(200, json=llm_reply(("symptom.guide", "digestive")))).post(
        "/v1/chat/messages", json={"text": secret})
    assert secret not in caplog.text
    assert "symptom.guide" in caplog.text


def test_config_reports_llm_routing_flag():
    settings = LlmSettings(enabled=True, endpoints=(PRIMARY,), timeout_seconds=2)
    app.dependency_overrides[get_settings] = lambda: settings
    # /v1/config 는 get_settings() 를 직접 호출하므로 캐시된 설정으로 응답한다 — 키가 camelCase 로 나오는지만 본다
    res = TestClient(app).get("/v1/config")
    assert res.status_code == 200
    assert "llmRouting" in res.json()
