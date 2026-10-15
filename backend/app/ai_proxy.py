"""ai-backend(음성인식·외국어 답변·상담원 연결)로 /v1 일부 경로를 넘기는 프록시.

화면과 API 를 한 주소(같은 출처)로 주는 팀 backend 가 아래 경로만 ai-backend 로 전달한다.
- 환경변수 AI_BACKEND_URL (예: http://ai-backend:8100)이 있을 때만 켜진다. 비어 있으면 아무 일도 하지 않는다.
- 아래 목록에 있는 경로만 넘긴다. /v1/config, /v1/chat/messages 처럼 팀 backend 가 직접 처리하는 경로는 건드리지 않는다.
- 질문·음성·상담 내용은 로그에 남기지 않는다(경로와 상태 코드만).
"""
import asyncio
import logging
import os
import time
from collections import defaultdict, deque

import httpx
import websockets
from fastapi import APIRouter, Request, WebSocket
from starlette.responses import JSONResponse, Response

logger = logging.getLogger(__name__)

# (경로, 메서드) — ai-backend/README.md 의 API 표와 같다
HTTP_ROUTES: list[tuple[str, list[str]]] = [
    ("/v1/stt", ["POST"]),
    ("/v1/chat", ["POST"]),
    ("/v1/chat/foreign", ["POST"]),
    ("/v1/voice/config", ["GET"]),
    ("/v1/handoff/status", ["GET"]),
    ("/v1/handoff", ["POST"]),
    ("/v1/agent/login", ["POST"]),
    ("/v1/agent/callbacks", ["GET"]),
    ("/v1/agent/callbacks/{callback_id}/done", ["POST"]),
    ("/v1/callbacks", ["POST"]),
]
WS_ROUTES = ["/v1/handoff/ws/{ticket}", "/v1/agent/ws"]

# 요청·응답에서 그대로 옮기면 안 되는 헤더 (연결 단위 헤더, 길이·압축은 다시 계산)
_SKIP_REQUEST = {
    "host", "connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te", "trailers",
    "transfer-encoding", "upgrade", "content-length", "accept-encoding",
}
_SKIP_RESPONSE = {"connection", "keep-alive", "transfer-encoding", "content-length", "content-encoding"}

DEFAULT_RATE_LIMIT = 20            # IP 당 분당 POST 수 (ai-backend 기본값과 같다). 0 이면 끔
DEFAULT_MAX_BODY = 3 * 1024 * 1024  # 음성(최대 2MB)과 여유


def make_router(
    base_url: str,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
    rate_limit_per_minute: int | None = None,
    max_body_bytes: int = DEFAULT_MAX_BODY,
    allowed_origins: list[str] | None = None,
) -> APIRouter:
    base = base_url.rstrip("/")
    ws_base = base.replace("https://", "wss://", 1).replace("http://", "ws://", 1)
    limit = DEFAULT_RATE_LIMIT if rate_limit_per_minute is None else rate_limit_per_minute
    origins = set(allowed_origins or [])
    router = APIRouter()
    client = httpx.AsyncClient(base_url=base, transport=transport, timeout=httpx.Timeout(120.0, connect=5.0))
    hits: dict[str, deque[float]] = defaultdict(deque)

    def limited(ip: str) -> bool:
        if limit <= 0:
            return False
        now = time.monotonic()
        q = hits[ip]
        while q and now - q[0] > 60:
            q.popleft()
        if len(q) >= limit:
            return True
        q.append(now)
        return False

    async def forward(request: Request) -> Response:
        ip = request.client.host if request.client else "?"
        if request.method == "POST" and limited(ip):
            return JSONResponse(status_code=429, content={
                "error_code": "RATE_LIMITED", "message": "요청이 너무 많아요. 잠시 후 다시 시도해 주세요."})
        declared = request.headers.get("content-length")
        if declared and declared.isdigit() and int(declared) > max_body_bytes:
            return JSONResponse(status_code=413, content={"error_code": "TOO_LARGE", "message": "요청이 너무 큽니다."})
        body = await request.body()
        if len(body) > max_body_bytes:
            return JSONResponse(status_code=413, content={"error_code": "TOO_LARGE", "message": "요청이 너무 큽니다."})

        headers = {k: v for k, v in request.headers.items() if k.lower() not in _SKIP_REQUEST}
        headers["x-forwarded-host"] = request.headers.get("host", "")
        headers["x-forwarded-for"] = ip
        headers["x-forwarded-proto"] = request.url.scheme
        target = request.url.path + (f"?{request.url.query}" if request.url.query else "")
        try:
            upstream = await client.request(request.method, target, content=body, headers=headers)
        except httpx.HTTPError as e:
            logger.warning("ai-backend 요청 실패: %s %s (%s)", request.method, request.url.path, type(e).__name__)
            return JSONResponse(status_code=502, content={
                "error_code": "AI_BACKEND_UNAVAILABLE", "message": "지금은 이 기능을 사용할 수 없어요. 잠시 후 다시 시도해 주세요."})
        out = {k: v for k, v in upstream.headers.items() if k.lower() not in _SKIP_RESPONSE}
        return Response(content=upstream.content, status_code=upstream.status_code, headers=out)

    for path, methods in HTTP_ROUTES:
        router.add_api_route(path, forward, methods=methods, include_in_schema=False)

    def origin_ok(ws: WebSocket) -> bool:
        # WebSocket 은 CORS 가 적용되지 않으므로 Origin 을 직접 확인한다 (없으면 같은 사이트로 본다)
        origin = ws.headers.get("origin")
        if not origin:
            return True
        host = ws.headers.get("host", "")
        return origin in origins or origin.endswith("//" + host)

    async def ws_forward(ws: WebSocket) -> None:
        if not origin_ok(ws):
            await ws.close(code=1008)
            return
        target = ws_base + ws.url.path + (f"?{ws.url.query}" if ws.url.query else "")
        try:
            # 업스트림의 Origin 검사는 같은 사이트 기준이므로 업스트림 자신의 출처로 맞춘다
            up = await websockets.connect(target, origin=base, open_timeout=5, max_size=2**22)
        except Exception as e:  # 거절·연결 실패 모두 같은 처리 — 내용은 로그에 남기지 않는다
            logger.warning("ai-backend WebSocket 연결 실패: %s (%s)", ws.url.path, type(e).__name__)
            await ws.close(code=1011)
            return
        await ws.accept()

        async def client_to_upstream() -> None:
            while True:
                m = await ws.receive()
                if m["type"] == "websocket.disconnect":
                    return
                if m.get("text") is not None:
                    await up.send(m["text"])
                elif m.get("bytes") is not None:
                    await up.send(m["bytes"])

        async def upstream_to_client() -> None:
            while True:
                m = await up.recv()
                if isinstance(m, bytes):
                    await ws.send_bytes(m)
                else:
                    await ws.send_text(m)

        tasks = [asyncio.create_task(client_to_upstream()), asyncio.create_task(upstream_to_client())]
        try:
            await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for t in tasks:
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            code = getattr(up, "close_code", None) or 1000
            await up.close()
            try:
                await ws.close(code=code if 1000 <= code < 5000 else 1000)
            except RuntimeError:
                pass   # 이미 닫힘

    for path in WS_ROUTES:
        router.add_api_websocket_route(path, ws_forward)

    return router


def router_from_env() -> APIRouter | None:
    """AI_BACKEND_URL 이 있으면 프록시 라우터를, 없으면 None 을 돌려준다."""
    url = os.getenv("AI_BACKEND_URL", "").strip()
    if not url:
        return None
    origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]
    rate = os.getenv("AI_RATE_LIMIT_PER_MINUTE", "").strip()
    return make_router(url, rate_limit_per_minute=int(rate) if rate.isdigit() else None, allowed_origins=origins)
