import logging
import time
from functools import lru_cache

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field

from app.features.chat.service import IntentClassifier, LlmUnavailable
from app.features.chat.settings import LlmSettings, load_settings
from app.features.config.schemas import CamelModel

log = logging.getLogger("chat.api")
router = APIRouter(prefix="/v1", tags=["chat"])


class MessageIn(CamelModel):
    # 증상 문장이 올 수 있으므로 길이를 제한하고 로그에는 남기지 않는다
    text: str = Field(min_length=1, max_length=300)


class IntentOut(CamelModel):
    intent: str
    label: str
    topic: str | None = None


class MessageOut(CamelModel):
    intents: list[IntentOut]


@lru_cache
def get_settings() -> LlmSettings:
    return load_settings()


@lru_cache
def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient()


def get_classifier(settings: LlmSettings = Depends(get_settings)) -> IntentClassifier:
    return IntentClassifier(settings, _client())


@router.post("/chat/messages", response_model=MessageOut, response_model_by_alias=True)
async def post_message(body: MessageIn, classifier: IntentClassifier = Depends(get_classifier),
                       settings: LlmSettings = Depends(get_settings)) -> MessageOut:
    """질문 한 문장을 기능 목록(최대 3개, 말한 순서)으로 분류한다.

    LLM 이 꺼져 있거나 응답하지 않으면 503 — 프론트는 이때 키워드 규칙으로 대체한다.
    """
    if not settings.enabled:
        raise HTTPException(status_code=503, detail="llm_disabled")
    started = time.perf_counter()
    try:
        items = await classifier.classify(body.text.strip())
    except LlmUnavailable as err:
        raise HTTPException(status_code=503, detail="llm_unavailable") from err
    log.info("intents=%s ms=%d", [i.intent for i in items], (time.perf_counter() - started) * 1000)
    return MessageOut(intents=[IntentOut(intent=i.intent, label=i.label, topic=i.topic) for i in items])
