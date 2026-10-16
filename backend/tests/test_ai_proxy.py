"""ai-backend(음성인식·외국어 답변·상담원 연결)로 /v1 일부 경로를 넘기는 프록시.

가짜 ai-backend(작은 FastAPI 앱)를 두고, 요청이 그대로 전달되는지·오류와 제한이 지켜지는지 확인한다.
WebSocket 은 실제 서버를 스레드로 띄워 시험한다.
"""
import asyncio
import socket
import threading
import time

import httpx
import pytest
import uvicorn
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.ai_proxy import make_router


def make_upstream() -> FastAPI:
    up = FastAPI()

    @up.api_route("/v1/chat", methods=["POST"])
    async def chat(request: Request):
        body = await request.body()
        return {
            "path": request.url.path, "query": request.url.query, "method": request.method,
            "content_type": request.headers.get("content-type"), "size": len(body),
            "xfh": request.headers.get("x-forwarded-host"), "xff": request.headers.get("x-forwarded-for"),
            "auth": request.headers.get("authorization"), "host": request.headers.get("host"),
        }

    @up.post("/v1/stt")
    async def stt(request: Request):
        data = await request.body()
        return JSONResponse({"echo_len": len(data), "head": list(data[:4])}, headers={"X-Upstream": "1"})

    @up.get("/v1/handoff/status")
    async def status():
        return {"open": True}

    @up.post("/v1/callbacks")
    async def callbacks():
        return JSONResponse({"error_code": "BAD_PHONE"}, status_code=422)

    @up.websocket("/v1/handoff/ws/{ticket}")
    async def ws(sock: WebSocket, ticket: str):
        if ticket == "bad":
            await sock.close(code=4403)
            return
        await sock.accept()
        try:
            while True:
                m = await sock.receive()
                if m["type"] == "websocket.disconnect":
                    break
                if m.get("text") is not None:
                    await sock.send_text(f"{ticket}:{m['text']}")
                elif m.get("bytes") is not None:
                    await sock.send_bytes(m["bytes"][::-1])
        except WebSocketDisconnect:
            pass

    return up


def client_for(upstream: FastAPI, **kw) -> TestClient:
    app = FastAPI()
    transport = httpx.ASGITransport(app=upstream)
    app.include_router(make_router("http://ai.test", transport=transport, **kw))
    return TestClient(app)


# ── HTTP ─────────────────────────────────────────────────────────────

def test_json_post_is_forwarded_with_query_and_headers():
    c = client_for(make_upstream())
    res = c.post("/v1/chat?lang=en", json={"message": "hello"}, headers={"Authorization": "Bearer t0k"})
    assert res.status_code == 200
    body = res.json()
    assert body["path"] == "/v1/chat" and body["query"] == "lang=en" and body["method"] == "POST"
    assert body["content_type"].startswith("application/json")
    assert body["auth"] == "Bearer t0k"                       # 상담원 토큰이 그대로 간다
    assert body["xfh"] == "testserver"                        # 원래 주소를 알려 준다
    assert body["xff"]                                        # 접속자 IP 를 알려 준다
    assert body["host"] != "testserver"                       # Host 는 업스트림 것으로 바뀐다


def test_binary_body_and_upstream_headers_are_preserved():
    c = client_for(make_upstream())
    audio = bytes([1, 2, 3, 4, 0, 255]) * 100
    res = c.post("/v1/stt", files={"audio": ("v.webm", audio, "audio/webm")})
    assert res.status_code == 200
    assert res.json()["echo_len"] > len(audio)                # multipart 전체가 전달됨
    assert res.headers["x-upstream"] == "1"


def test_upstream_error_status_and_body_are_returned_as_is():
    c = client_for(make_upstream())
    res = c.post("/v1/callbacks", json={"phone": "x"})
    assert res.status_code == 422
    assert res.json() == {"error_code": "BAD_PHONE"}


def test_get_route_is_forwarded():
    c = client_for(make_upstream())
    assert c.get("/v1/handoff/status").json() == {"open": True}


def test_upstream_down_gives_502_json():
    app = FastAPI()
    app.include_router(make_router("http://127.0.0.1:9"))   # 닫힌 포트
    res = TestClient(app).post("/v1/chat", json={"message": "x"})
    assert res.status_code == 502
    assert res.json()["error_code"] == "AI_BACKEND_UNAVAILABLE"


def test_only_listed_routes_are_proxied():
    router = make_router("http://ai.test")
    paths = {getattr(r, "path", "") for r in router.routes}
    assert "/v1/stt" in paths and "/v1/chat" in paths and "/v1/handoff/ws/{ticket}" in paths
    # 팀 backend 가 직접 처리하는 경로는 넘기지 않는다
    assert "/v1/config" not in paths and "/v1/chat/messages" not in paths and "/health" not in paths


def test_rate_limit_applies_to_post_only():
    c = client_for(make_upstream(), rate_limit_per_minute=2)
    assert c.post("/v1/chat", json={}).status_code == 200
    assert c.post("/v1/chat", json={}).status_code == 200
    res = c.post("/v1/chat", json={})
    assert res.status_code == 429 and res.json()["error_code"] == "RATE_LIMITED"
    assert c.get("/v1/handoff/status").status_code == 200   # GET 은 세지 않는다


def test_rate_limit_zero_means_off():
    c = client_for(make_upstream(), rate_limit_per_minute=0)
    assert all(c.post("/v1/chat", json={}).status_code == 200 for _ in range(30))


def test_too_large_body_is_rejected():
    c = client_for(make_upstream(), max_body_bytes=1000)
    res = c.post("/v1/stt", content=b"x" * 5000, headers={"content-type": "application/octet-stream"})
    assert res.status_code == 413


# ── WebSocket (실제 서버 사용) ─────────────────────────────────────────

class RunningServer:
    def __init__(self, app):
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.port = self.sock.getsockname()[1]
        self.server = uvicorn.Server(uvicorn.Config(app, log_level="warning"))
        self.thread = threading.Thread(target=lambda: asyncio.run(self.server.serve(sockets=[self.sock])), daemon=True)

    def __enter__(self):
        self.thread.start()
        for _ in range(100):
            if self.server.started:
                return self
            time.sleep(0.05)
        raise RuntimeError("테스트 서버가 시작되지 않았습니다")

    def __exit__(self, *exc):
        self.server.should_exit = True
        self.thread.join(timeout=5)


@pytest.fixture
def ws_client():
    with RunningServer(make_upstream()) as up:
        app = FastAPI()
        app.include_router(make_router(f"http://127.0.0.1:{up.port}"))
        yield TestClient(app)


def test_websocket_text_and_binary_pass_through(ws_client):
    with ws_client.websocket_connect("/v1/handoff/ws/t1") as ws:
        ws.send_text("안녕")
        assert ws.receive_text() == "t1:안녕"
        ws.send_bytes(b"abc")
        assert ws.receive_bytes() == b"cba"


def test_websocket_rejected_by_upstream_is_closed(ws_client):
    # 업스트림이 곧바로 닫는 티켓: 클라이언트는 연결 후 닫힘 신호를 받는다
    with pytest.raises(Exception):
        with ws_client.websocket_connect("/v1/handoff/ws/bad") as ws:
            ws.receive_text()


def test_websocket_from_other_site_is_rejected(ws_client):
    with pytest.raises(Exception):
        with ws_client.websocket_connect("/v1/handoff/ws/t1", headers={"origin": "http://evil.example"}) as ws:
            ws.receive_text()


def test_websocket_same_site_origin_is_accepted(ws_client):
    with ws_client.websocket_connect("/v1/handoff/ws/t2", headers={"origin": "http://testserver"}) as ws:
        ws.send_text("x")
        assert ws.receive_text() == "t2:x"
