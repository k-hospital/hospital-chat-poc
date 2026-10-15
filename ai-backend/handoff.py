"""
상담원 연결 (국내 전용, 한국어) — 대기열·실시간 대화를 메모리에서만 관리한다.

  - 대화 내용은 저장하지 않는다: 상담이 끝나거나 서버가 재시작되면 사라진다. 로그에도 본문을 남기지 않는다.
  - 상담원 1명이 동시에 최대 config.HANDOFF_MAX_CHATS_PER_AGENT건.
  - 연결이 잠깐 끊겨도(새로고침·네트워크) HANDOFF_GRACE_SECONDS 안에 다시 붙으면 이어진다.

WebSocket 메시지 (JSON)
  이용자 /v1/handoff/ws/{ticket}
    서버→이용자: queue{position} · connected · message{from:"agent",text,ts} · closed{by} · error{message}
    이용자→서버: message{text} · close
  상담원 /v1/agent/ws?token=
    서버→상담원: init{waiting,chats} · waiting{items} · assigned{chat} · message{ticket,from:"user",text,ts}
                 user_left{ticket} · user_back{ticket} · closed{ticket,by} · error{message}
    상담원→서버: accept{ticket} · message{ticket,text} · close{ticket}
"""

from __future__ import annotations

import asyncio
import logging
import secrets
import time
from dataclasses import dataclass, field
from datetime import datetime

from fastapi import WebSocket

import config as C

logger = logging.getLogger("global_chatbot.handoff")


def _now() -> float:
    return time.time()


@dataclass
class Ticket:
    id: str
    created: float
    transcript: list[dict]                 # 챗봇과 나눈 대화 [{role: user|bot, text}]
    status: str = "waiting"                # waiting | active | closed
    messages: list[dict] = field(default_factory=list)   # [{from: user|agent|system, text, ts}]
    agent: str | None = None               # 상담원 토큰
    user_ws: WebSocket | None = None
    user_gone_at: float | None = None      # 이용자 연결이 끊긴 시각 (다시 붙으면 None)

    def summary(self) -> dict:
        first = next((t["text"] for t in self.transcript if t.get("role") == "user"), "")
        return {"ticket": self.id, "created": self.created, "preview": first[:60]}

    def detail(self) -> dict:
        return {"ticket": self.id, "created": self.created, "transcript": self.transcript,
                "messages": self.messages, "user_online": self.user_ws is not None}


@dataclass
class Agent:
    token: str
    name: str
    expires: float
    ws: WebSocket | None = None
    gone_at: float | None = None


class HandoffManager:
    def __init__(self) -> None:
        self.tickets: dict[str, Ticket] = {}
        self.agents: dict[str, Agent] = {}      # token → Agent (로그인 세션)
        self.lock = asyncio.Lock()

    # ------------------------------------------------------------ 운영 여부
    def is_open_hours(self, now: datetime | None = None) -> bool:
        if C.HANDOFF_ALWAYS_OPEN:
            return True
        now = now or datetime.now()
        if now.weekday() not in C.HANDOFF_WEEKDAYS:
            return False
        hhmm = now.strftime("%H:%M")
        return C.HANDOFF_OPEN <= hhmm < C.HANDOFF_CLOSE

    def online_agents(self) -> int:
        return sum(1 for a in self.agents.values() if a.ws is not None)

    def availability(self) -> dict:
        if not self.is_open_hours():
            reason = "closed_hours"
        elif self.online_agents() == 0:
            reason = "no_agent"
        else:
            reason = None
        return {"available": reason is None, "reason": reason, "hours_text": C.HANDOFF_HOURS_TEXT}

    # ------------------------------------------------------------ 상담원 로그인
    def login(self, name: str) -> str:
        token = secrets.token_urlsafe(24)
        self.agents[token] = Agent(token=token, name=name, expires=_now() + C.AGENT_SESSION_HOURS * 3600)
        return token

    def agent_of(self, token: str | None) -> Agent | None:
        a = self.agents.get(token or "")
        if a and a.expires > _now():
            return a
        if a:
            self.agents.pop(a.token, None)
        return None

    # ------------------------------------------------------------ 대기열
    def waiting(self) -> list[Ticket]:
        return sorted((t for t in self.tickets.values() if t.status == "waiting"), key=lambda t: t.created)

    def position(self, ticket: Ticket) -> int:
        w = self.waiting()
        return w.index(ticket) + 1 if ticket in w else 0

    def create(self, transcript: list[dict]) -> Ticket:
        t = Ticket(id=secrets.token_urlsafe(16), created=_now(), transcript=transcript)
        t.user_gone_at = _now()      # 이용자 WebSocket이 붙기 전까지는 '끊김' 상태 (안 붙으면 정리됨)
        self.tickets[t.id] = t
        return t

    def chats_of(self, agent: Agent) -> list[Ticket]:
        return [t for t in self.tickets.values() if t.status == "active" and t.agent == agent.token]

    # ------------------------------------------------------------ 전송
    @staticmethod
    async def _send(ws: WebSocket | None, payload: dict) -> None:
        if ws is None:
            return
        try:
            await ws.send_json(payload)
        except Exception:   # 끊긴 소켓 — 정리는 연결 종료 처리에서
            pass

    async def broadcast_queue(self) -> None:
        """상담원 전원에게 대기 목록, 대기 중 이용자에게 순번."""
        items = [t.summary() for t in self.waiting()]
        for a in list(self.agents.values()):
            await self._send(a.ws, {"type": "waiting", "items": items})
        for i, t in enumerate(self.waiting(), start=1):
            await self._send(t.user_ws, {"type": "queue", "position": i})

    # ------------------------------------------------------------ 이용자
    async def user_join(self, t: Ticket, ws: WebSocket) -> None:
        old = t.user_ws
        t.user_ws, t.user_gone_at = ws, None
        if old is not None and old is not ws:
            try:
                await old.close()
            except Exception:
                pass
        if t.status == "waiting":
            await self.broadcast_queue()      # 이 이용자에게 순번도 함께 보냄
        elif t.status == "active":
            await self._send(ws, {"type": "connected", "messages": t.messages})
            a = self.agents.get(t.agent or "")
            await self._send(a.ws if a else None, {"type": "user_back", "ticket": t.id})

    async def user_leave(self, t: Ticket, ws: WebSocket) -> None:
        if t.user_ws is not ws:
            return
        t.user_ws, t.user_gone_at = None, _now()
        if t.status == "active":
            a = self.agents.get(t.agent or "")
            await self._send(a.ws if a else None, {"type": "user_left", "ticket": t.id})

    async def user_message(self, t: Ticket, text: str) -> None:
        if t.status != "active":
            return
        m = {"from": "user", "text": text, "ts": _now()}
        t.messages.append(m)
        a = self.agents.get(t.agent or "")
        await self._send(a.ws if a else None, {"type": "message", "ticket": t.id, **m})

    # ------------------------------------------------------------ 상담원
    async def agent_join(self, a: Agent, ws: WebSocket) -> None:
        old = a.ws
        a.ws, a.gone_at = ws, None
        if old is not None and old is not ws:
            try:
                await old.close()
            except Exception:
                pass
        await self._send(ws, {"type": "init", "name": a.name, "max_chats": C.HANDOFF_MAX_CHATS_PER_AGENT,
                              "waiting": [t.summary() for t in self.waiting()],
                              "chats": [t.detail() for t in self.chats_of(a)]})

    async def agent_leave(self, a: Agent, ws: WebSocket) -> None:
        if a.ws is ws:
            a.ws, a.gone_at = None, _now()

    async def accept(self, a: Agent, ticket_id: str) -> None:
        async with self.lock:   # 두 상담원이 같은 대기표를 동시에 받지 않게
            t = self.tickets.get(ticket_id)
            if not t or t.status != "waiting":
                await self._send(a.ws, {"type": "error", "message": "이미 다른 상담원이 연결했거나 종료된 상담입니다."})
                return
            if len(self.chats_of(a)) >= C.HANDOFF_MAX_CHATS_PER_AGENT:
                await self._send(a.ws, {"type": "error",
                                        "message": f"동시에 {C.HANDOFF_MAX_CHATS_PER_AGENT}건까지 상담할 수 있습니다."})
                return
            t.status, t.agent = "active", a.token
            t.messages.append({"from": "system", "text": "상담원이 연결되었습니다.", "ts": _now()})
        await self._send(a.ws, {"type": "assigned", "chat": t.detail()})
        await self._send(t.user_ws, {"type": "connected", "messages": t.messages})
        await self.broadcast_queue()

    async def agent_message(self, a: Agent, ticket_id: str, text: str) -> None:
        t = self.tickets.get(ticket_id)
        if not t or t.status != "active" or t.agent != a.token:
            return
        m = {"from": "agent", "text": text, "ts": _now()}
        t.messages.append(m)
        await self._send(t.user_ws, {"type": "message", **m})

    # ------------------------------------------------------------ 종료·정리
    async def close(self, t: Ticket, by: str) -> None:
        if t.status == "closed":
            return
        was_waiting = t.status == "waiting"
        t.status = "closed"
        await self._send(t.user_ws, {"type": "closed", "by": by})
        a = self.agents.get(t.agent or "")
        await self._send(a.ws if a else None, {"type": "closed", "ticket": t.id, "by": by})
        self.tickets.pop(t.id, None)      # 대화 내용 즉시 삭제
        if was_waiting:
            await self.broadcast_queue()

    async def sweep(self) -> None:
        """끊긴 지 오래된 이용자·상담원 정리 (주기 실행)."""
        now = _now()
        grace = C.HANDOFF_GRACE_SECONDS
        for t in list(self.tickets.values()):
            if t.user_gone_at and now - t.user_gone_at > grace:
                await self.close(t, "user_left")
        for a in list(self.agents.values()):
            if a.expires <= now:
                self.agents.pop(a.token, None)
            if a.ws is None and a.gone_at and now - a.gone_at > grace:
                a.gone_at = None
                # 돌아오지 않은 상담원의 상담은 대기열 맨 앞으로 되돌린다
                for t in self.chats_of(a):
                    t.status, t.agent = "waiting", None
                    t.created = 0.0
                    t.messages.append({"from": "system", "text": "상담원 연결이 끊어져 다시 대기합니다.", "ts": now})
                    await self._send(t.user_ws, {"type": "requeued"})
                await self.broadcast_queue()

    async def run_sweeper(self) -> None:
        while True:
            await asyncio.sleep(10)
            try:
                await self.sweep()
            except Exception as e:   # 정리 실패가 서버를 멈추지 않게
                logger.error("handoff sweep failed: %s", type(e).__name__)


manager = HandoffManager()
