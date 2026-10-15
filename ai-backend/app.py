"""
외국어·음성 백엔드 (FastAPI) — 메인 화면의 마이크 버튼과 음성 번역에 쓰는 API

  GET  /v1/voice/config    지원 언어·제한값 (화면 표시용)
  POST /v1/stt             녹음 파일 -> {text, language, duration, route}
                             route: "korean"(메인 챗봇으로) | "foreign"(/v1/chat/foreign으로) | "unsupported"
  POST /v1/chat            {message, lang?} -> 한국어·외국어 통합 답변 (화면·음성 공통 입구)
                             한국어: RAG -> 카나나 3B / 영어·중국어: /v1/chat/foreign과 같은 흐름
  POST /v1/chat/foreign    {message, lang?} -> 그 언어로 답변 (D안: 번역+검색어 확장 -> RAG -> Qwen3.6)
  GET  /v1/health          {"status": "ok"}

  상담원 연결 (국내 전용, 대화는 메모리에만 — handoff.py)
  GET  /v1/handoff/status               {available, reason: closed_hours|no_agent|null, hours_text}
  POST /v1/handoff                      {transcript} -> {available, ticket?, position?}
  WS   /v1/handoff/ws/{ticket}          이용자 실시간 대화
  POST /v1/callbacks                    {phone, preferred_time, note?, consent} 콜백 요청 (SQLite, 7일 후 자동 삭제)
  POST /v1/agent/login                  {password, name} -> {token}
  WS   /v1/agent/ws?token=              상담원 실시간 (대기 목록·대화)
  GET  /v1/agent/callbacks              (Bearer) 콜백 목록      POST /v1/agent/callbacks/{id}/done  처리 완료(삭제)

원칙: 질문 본문·음성은 저장하지 않고 로그에도 남기지 않는다. 오류는 코드 + 사용자 언어 안내문만 보낸다.

실행 (hospital_chatbot/backend 폴더에서):
    pip install -r requirements.txt
    uvicorn app:app --host 127.0.0.1 --port 8100
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager

import asyncio
import hmac

import httpx
from fastapi import FastAPI, File, Form, Header, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from qdrant_client import AsyncQdrantClient

import callbacks as CB
import config as C
import handoff as H
import prompts as P
import rag
import stt
import translate as T

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("global_chatbot")
# httpx 기본 로그는 요청 주소만 남지만, 질문이 들어가는 경우는 없도록 WARNING 이상만
logging.getLogger("httpx").setLevel(logging.WARNING)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.http = httpx.AsyncClient(timeout=C.HTTP_TIMEOUT_SECONDS)
    app.state.qdrant = AsyncQdrantClient(url=C.QDRANT_URL)
    logger.info("startup (langs=%s, collection=%s)", C.SUPPORTED_LANGS, C.QDRANT_COLLECTION)
    missing = [n for n in ("QDRANT_URL", "DENSE_EMBEDDING_URL", "SPARSE_EMBEDDING_URL", "RERANKER_URL",
                           "LLM_BASE_URL", "LLM_MODEL", "KO_LLM_BASE_URL", "KO_LLM_MODEL", "STT_URL", "STT_MODEL")
               if not getattr(C, n)]
    if missing:   # 사내 서버 주소·모델은 .env 에서만 설정 (.env.example 참고)
        logger.error("설정 누락: %s — ai-backend/.env 를 확인하세요", ", ".join(missing))
    if not C.AGENT_PASSWORD:
        logger.warning("AGENT_PASSWORD가 비어 있어 상담원 로그인이 막혀 있습니다")
    CB.purge_old()
    sweeper = asyncio.create_task(H.manager.run_sweeper())
    try:
        yield
    finally:
        sweeper.cancel()
        await app.state.http.aclose()
        await app.state.qdrant.close()


app = FastAPI(
    title="global voice & translation API",
    lifespan=lifespan,
    docs_url="/docs" if C.ENABLE_DOCS else None,
    redoc_url=None,
    openapi_url="/openapi.json" if C.ENABLE_DOCS else None,
)
app.add_middleware(CORSMiddleware, allow_origins=C.CORS_ORIGINS, allow_methods=["GET", "POST"],
                   allow_headers=["Content-Type", "Authorization"])


# ---------------------------------------------------------------- 공통: 오류·보안·요청 제한

class ApiError(Exception):
    def __init__(self, status: int, code: str, lang: str | None = None, **fmt):
        self.status, self.code, self.lang, self.fmt = status, code, lang, fmt


def _message(code: str, lang: str | None, **fmt) -> str:
    table = (P.KO if lang == "ko" else P.LANGS.get(lang or "", P.LANGS[C.DEFAULT_LANG]))["errors"]
    return table.get(code, table["SERVICE_UNAVAILABLE"]).format(**fmt)


@app.exception_handler(ApiError)
async def _api_error(_: Request, e: ApiError):
    return JSONResponse(status_code=e.status,
                        content={"error_code": e.code, "message": _message(e.code, e.lang, **e.fmt)})


@app.exception_handler(rag.PipelineError)
async def _pipeline_error(request: Request, e: rag.PipelineError):
    # 내부 단계·원인은 서버 로그에만 (본문 없음). 사용자에게는 코드만.
    logger.error("pipeline failed stage=%s detail=%s path=%s", e.stage, e.detail, request.url.path)
    lang = getattr(request.state, "lang", None)
    return JSONResponse(status_code=502, content={
        "error_code": f"UPSTREAM_{e.stage.upper()}", "message": _message("SERVICE_UNAVAILABLE", lang)})


_hits: dict[str, deque] = defaultdict(deque)


@app.middleware("http")
async def _guard(request: Request, call_next):
    if C.RATE_LIMIT_PER_MINUTE > 0 and request.method == "POST":
        ip = request.client.host if request.client else "?"
        now = time.monotonic()
        q = _hits[ip]
        while q and now - q[0] > 60:
            q.popleft()
        if len(q) >= C.RATE_LIMIT_PER_MINUTE:
            return JSONResponse(status_code=429, content={
                "error_code": "RATE_LIMITED", "message": _message("RATE_LIMITED", None)})
        q.append(now)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store"
    return response


# ---------------------------------------------------------------- 라우트

@app.get("/v1/health")
async def health():
    return {"status": "ok"}


@app.get("/v1/voice/config")
async def voice_config():
    return {
        "languages": [{"code": c, "name": P.LANGS[c]["name"]} for c in C.SUPPORTED_LANGS if c in P.LANGS],
        "default_language": C.DEFAULT_LANG,
        "max_message_chars": C.MAX_MESSAGE_CHARS,
        "max_audio_seconds": C.MAX_AUDIO_SECONDS,
        "max_audio_bytes": C.MAX_AUDIO_BYTES,
        "notices": {c: {"disclaimer": P.LANGS[c]["disclaimer"], "emergency": P.LANGS[c]["emergency"]}
                    for c in C.SUPPORTED_LANGS if c in P.LANGS},
    }


def _route_for(lang: str | None) -> str:
    if lang == "ko":
        return "korean"
    return "foreign" if lang in C.SUPPORTED_LANGS else "unsupported"


@app.post("/v1/stt")
async def speech_to_text(request: Request, audio: UploadFile = File(...),
                         lang_hint: str | None = Form(default=None)):
    """lang_hint: 화면 언어를 알면 넣는다 (ko/en/zh). 비우면 Whisper가 언어를 감지 (조금 더 느림)."""
    hint = (lang_hint or "").strip().lower() or None
    if hint and hint != "ko" and hint not in C.SUPPORTED_LANGS:
        hint = None
    request.state.lang = hint
    data = await audio.read(C.MAX_AUDIO_BYTES + 1)
    if len(data) > C.MAX_AUDIO_BYTES:
        raise ApiError(413, "AUDIO_TOO_LARGE", hint, seconds=C.MAX_AUDIO_SECONDS)
    if not data:
        raise ApiError(400, "AUDIO_EMPTY", hint)

    t0 = time.perf_counter()
    result = await stt.transcribe(request.app.state.http, data, audio.filename or "audio.webm",
                                  audio.content_type or "", hint)
    logger.info("stt ok lang=%s audio_s=%s took=%.1fs", result["language"], result["duration"],
                time.perf_counter() - t0)
    if not result["text"]:
        raise ApiError(422, "AUDIO_EMPTY", result["language"])
    return {**result, "route": _route_for(result["language"])}


class ForeignChatRequest(BaseModel):
    message: str
    lang: str | None = None   # 화면 언어 (선택). 실제 답변 언어는 질문 문자로 판별한 언어를 우선


@app.post("/v1/chat/foreign")
async def chat_foreign(request: Request, req: ForeignChatRequest):
    text = (req.message or "").strip()
    hint = (req.lang or "").strip().lower() or None
    request.state.lang = hint if hint in C.SUPPORTED_LANGS else None
    if not text:
        raise ApiError(400, "EMPTY_MESSAGE", request.state.lang)
    if len(text) > C.MAX_MESSAGE_CHARS:
        raise ApiError(400, "MESSAGE_TOO_LONG", request.state.lang, limit=C.MAX_MESSAGE_CHARS)

    detected = T.detect_lang(text)
    # 라틴 문자는 영어 외 언어일 수도 있으므로, 화면 언어가 주어지면 그쪽을 따른다
    lang = hint if (detected == "en" and hint in C.SUPPORTED_LANGS) else detected
    if lang == "ko":
        # 한국어 질문은 메인 챗봇이 처리 (화면이 그쪽으로 보내도록 코드로 알려 줌)
        return JSONResponse(status_code=409, content={"error_code": "USE_KOREAN_CHATBOT", "route": "korean",
                                                      "message": "한국어 질문은 메인 챗봇으로 보내 주세요."})
    if lang not in C.SUPPORTED_LANGS:
        raise ApiError(400, "UNSUPPORTED_LANGUAGE", request.state.lang)
    request.state.lang = lang
    return await _answer_foreign(request, text, lang)


async def _answer_foreign(request: Request, text: str, lang: str) -> dict:
    t0 = time.perf_counter()
    client, qdrant = request.app.state.http, request.app.state.qdrant
    ko, kw = await T.translate_and_expand(client, text)
    query = f"{ko} {kw}".strip()
    points = await rag.search(client, qdrant, query, query if C.RERANK_WITH_KEYWORDS else ko)
    reply, rewritten = await T.answer(client, lang, text, rag.build_context(points))
    emergency = T.has_emergency(text, ko)
    logger.info("chat ok lang=%s refs=%d emergency=%s rewritten=%s took=%.1fs", lang, len(points), emergency,
                rewritten, time.perf_counter() - t0)

    L = P.LANGS[lang]
    return {
        "lang": lang,
        "answer": reply,
        "sources": rag.sources_of(points),
        "emergency": L["emergency"] if emergency else None,
        "disclaimer": L["disclaimer"],
        "translated_notice": L["translated_notice"].format(center=C.INTL_CENTER_CONTACT),
        "query_ko": ko,   # 확인용: 검색에 쓴 한국어 질문 (화면에서는 접어 두거나 숨김)
    }


# ---------------------------------------------------------------- 통합 입구 (한국어 + 외국어)

class ChatRequest(BaseModel):
    message: str
    lang: str | None = None   # 화면 언어 또는 STT 감지 언어 (선택). 질문 문자로 판별한 언어를 우선


async def _answer_korean(request: Request, text: str) -> dict:
    t0 = time.perf_counter()
    client, qdrant = request.app.state.http, request.app.state.qdrant
    kw = ""
    if C.KO_EXPAND_KEYWORDS:
        _, kw = await T.translate_and_expand(client, text)
    query = f"{text} {kw}".strip()
    points = await rag.search(client, qdrant, query, query if C.RERANK_WITH_KEYWORDS else text)
    context = rag.build_context(points, C.KO_MAX_CHUNK_CHARS, C.KO_MAX_CONTEXT_CHARS, korean=True)
    kind = P.question_kind_ko(text)
    reply = await T.answer_korean(client, text, context, kind)
    emergency = T.has_emergency(text)
    logger.info("chat ok lang=ko kind=%s refs=%d emergency=%s expand=%s took=%.1fs", kind, len(points), emergency,
                bool(kw), time.perf_counter() - t0)
    return {
        "lang": "ko",
        "answer": reply,
        "sources": rag.sources_of(points),
        "emergency": P.KO["emergency"] if emergency else None,
        "disclaimer": P.KO["disclaimer"],
        "translated_notice": None,
        "query_ko": text,
    }


@app.post("/v1/chat")
async def chat(request: Request, req: ChatRequest):
    """문자 입력·음성(STT 결과) 공통. 응답 형식은 언어와 관계없이 같다 (/v1/chat/foreign과 같은 키)."""
    text = (req.message or "").strip()
    hint = (req.lang or "").strip().lower() or None
    request.state.lang = hint if (hint == "ko" or hint in C.SUPPORTED_LANGS) else None
    if not text:
        raise ApiError(400, "EMPTY_MESSAGE", request.state.lang)
    if len(text) > C.MAX_MESSAGE_CHARS:
        raise ApiError(400, "MESSAGE_TOO_LONG", request.state.lang, limit=C.MAX_MESSAGE_CHARS)

    detected = T.detect_lang(text)
    if detected == "en" and hint in C.SUPPORTED_LANGS:
        lang = hint            # 라틴 문자는 영어 외 언어일 수도 있어 화면 언어를 따른다
    elif detected == "unknown" and request.state.lang:
        lang = request.state.lang   # 숫자·기호만 있는 질문
    else:
        lang = detected
    if lang == "ko":
        request.state.lang = "ko"
        return await _answer_korean(request, text)
    if lang not in C.SUPPORTED_LANGS:
        raise ApiError(400, "UNSUPPORTED_LANGUAGE", request.state.lang)
    request.state.lang = lang
    return await _answer_foreign(request, text, lang)


# ---------------------------------------------------------------- 상담원 연결 (국내 전용)

def _ok_origin(ws: WebSocket) -> bool:
    """WebSocket은 CORS가 적용되지 않으므로 Origin을 직접 확인 (없으면 같은 사이트로 본다)."""
    origin = ws.headers.get("origin")
    return not origin or origin in C.CORS_ORIGINS or origin.endswith("//" + (ws.headers.get("host") or ""))


def _clip(text, limit: int) -> str:
    return (text if isinstance(text, str) else "").strip()[:limit]


@app.get("/v1/handoff/status")
async def handoff_status():
    return H.manager.availability()


class HandoffRequest(BaseModel):
    transcript: list[dict] = []


@app.post("/v1/handoff")
async def handoff_start(req: HandoffRequest):
    av = H.manager.availability()
    if not av["available"]:
        return av
    transcript = [{"role": "user" if t.get("role") == "user" else "bot", "text": _clip(t.get("text"), 1000)}
                  for t in req.transcript[-C.HANDOFF_MAX_TRANSCRIPT:] if isinstance(t, dict)]
    t = H.manager.create([x for x in transcript if x["text"]])
    await H.manager.broadcast_queue()
    logger.info("handoff created waiting=%d", len(H.manager.waiting()))
    return {**av, "ticket": t.id, "position": H.manager.position(t)}


@app.websocket("/v1/handoff/ws/{ticket}")
async def handoff_ws(ws: WebSocket, ticket: str):
    t = H.manager.tickets.get(ticket)
    if not _ok_origin(ws) or not t:
        await ws.close(code=4404)
        return
    await ws.accept()
    await H.manager.user_join(t, ws)
    try:
        while True:
            data = await ws.receive_json()
            kind = data.get("type") if isinstance(data, dict) else None
            if kind == "message":
                text = _clip(data.get("text"), C.MAX_MESSAGE_CHARS)
                if text:
                    await H.manager.user_message(t, text)
            elif kind == "close":
                await H.manager.close(t, "user")
                break
    except (WebSocketDisconnect, ValueError, RuntimeError):
        pass
    finally:
        await H.manager.user_leave(t, ws)


class AgentLogin(BaseModel):
    password: str
    name: str = "상담원"


@app.post("/v1/agent/login")
async def agent_login(req: AgentLogin):
    if not C.AGENT_PASSWORD or not hmac.compare_digest(req.password.encode(), C.AGENT_PASSWORD.encode()):
        return JSONResponse(status_code=401, content={"error_code": "LOGIN_FAILED",
                                                      "message": "비밀번호가 맞지 않습니다."})
    name = _clip(req.name, 20) or "상담원"
    return {"token": H.manager.login(name), "name": name}


def _agent_or_401(authorization: str | None):
    token = (authorization or "").removeprefix("Bearer ").strip()
    return H.manager.agent_of(token)


@app.websocket("/v1/agent/ws")
async def agent_ws(ws: WebSocket, token: str = ""):
    a = H.manager.agent_of(token)
    if not _ok_origin(ws) or not a:
        await ws.close(code=4401)
        return
    await ws.accept()
    await H.manager.agent_join(a, ws)
    try:
        while True:
            data = await ws.receive_json()
            if not isinstance(data, dict):
                continue
            kind, tid = data.get("type"), str(data.get("ticket") or "")
            if kind == "accept":
                await H.manager.accept(a, tid)
            elif kind == "message":
                text = _clip(data.get("text"), 1000)
                if text:
                    await H.manager.agent_message(a, tid, text)
            elif kind == "close":
                t = H.manager.tickets.get(tid)
                if t and t.agent == a.token:
                    await H.manager.close(t, "agent")
    except (WebSocketDisconnect, ValueError, RuntimeError):
        pass
    finally:
        await H.manager.agent_leave(a, ws)


class CallbackRequest(BaseModel):
    phone: str
    preferred_time: str
    note: str = ""
    consent: bool = False


@app.post("/v1/callbacks")
async def callback_create(req: CallbackRequest):
    if not req.consent:
        return JSONResponse(status_code=400, content={"error_code": "CONSENT_REQUIRED",
                                                      "message": "개인정보 수집에 동의해 주세요."})
    if not CB.valid_phone(req.phone):
        return JSONResponse(status_code=400, content={"error_code": "INVALID_PHONE",
                                                      "message": "전화번호를 다시 확인해 주세요. (예: 010-1234-5678)"})
    CB.add(req.phone, _clip(req.preferred_time, 50) or "언제든", _clip(req.note, 200))
    logger.info("callback created")
    return {"ok": True, "retention_days": C.CALLBACK_RETENTION_DAYS}


@app.get("/v1/agent/callbacks")
async def callback_list(authorization: str | None = Header(default=None)):
    if not _agent_or_401(authorization):
        return JSONResponse(status_code=401, content={"error_code": "UNAUTHORIZED", "message": "다시 로그인해 주세요."})
    return {"items": CB.list_all()}


@app.post("/v1/agent/callbacks/{callback_id}/done")
async def callback_done(callback_id: int, authorization: str | None = Header(default=None)):
    if not _agent_or_401(authorization):
        return JSONResponse(status_code=401, content={"error_code": "UNAUTHORIZED", "message": "다시 로그인해 주세요."})
    return {"ok": CB.done(callback_id)}
