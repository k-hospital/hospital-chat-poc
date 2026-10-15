"""질문 문장 → 기능(intent) 분류. 사내 LLM(OpenAI 호환 API)에 정해진 JSON 형식으로만 답하게 한다.

- 프롬프트·출력 스키마: 이 폴더의 intent_prompt.txt, intent_schema.json (평가 스크립트도 같은 파일을 읽는다)
- 질문 문장(증상 등)은 로그에 남기지 않는다. 기능 이름과 걸린 시간만 기록한다.
"""
import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path

import httpx

from app.features.chat.settings import LlmEndpoint, LlmSettings

log = logging.getLogger("chat.intent")

_HERE = Path(__file__).parent
PROMPT = (_HERE / "intent_prompt.txt").read_text(encoding="utf-8").strip()
SCHEMA = json.loads((_HERE / "intent_schema.json").read_text(encoding="utf-8"))

_ITEM_PROPS = SCHEMA["properties"]["intents"]["items"]["properties"]
INTENTS = frozenset(_ITEM_PROPS["intent"]["enum"])
TOPICS = frozenset(_ITEM_PROPS["topic"]["enum"])
MAX_INTENTS = SCHEMA["properties"]["intents"]["maxItems"]
# 주제를 쓰는 기능은 이 둘뿐이다 (그 밖의 기능에서 온 주제는 버린다)
TOPIC_INTENTS = frozenset({"symptom.guide", "info.directions"})

# 챗봇 화면에 보여 줄 기능 이름 (프론트의 메뉴 이름과 같게 둔다)
LABELS = {
    "booking.start": "진료 예약",
    "booking.lookup": "예약 조회",
    "symptom.guide": "증상별 진료 안내",
    "info.directions": "오시는 길",
    "faq.parking": "주차 안내",
    "faq.hours": "진료 시간",
    "faq.certificate": "증명서 발급",
    "doctor.search": "의료진 찾기",
    "info.outpatient": "외래 안내",
    "info.health": "건강검진 안내",
    "action.agent": "상담원 연결",
    "action.callback": "콜백 요청",
    "emergency": "응급",
    "unknown": "알 수 없음",
}


class LlmUnavailable(Exception):
    """모든 LLM 서버가 응답하지 않거나, 형식에 맞는 답을 주지 못했다."""


class LlmBadResponse(Exception):
    """응답은 왔지만 약속한 JSON 형식이 아니다."""


@dataclass(frozen=True)
class ResolvedIntent:
    intent: str
    label: str
    topic: str | None


def normalize(content: str) -> list[ResolvedIntent]:
    """LLM이 준 문자열을 검증해 기능 목록으로 바꾼다. 알 수 없는 값은 버린다."""
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip())
    try:
        raw = json.loads(text)
        items = raw["intents"]
    except (ValueError, KeyError, TypeError) as err:
        raise LlmBadResponse("JSON 형식이 아닙니다") from err
    if not isinstance(items, list):
        raise LlmBadResponse("intents 가 목록이 아닙니다")

    resolved: list[ResolvedIntent] = []
    seen: set[tuple[str, str | None]] = set()
    for item in items:
        if not isinstance(item, dict) or item.get("intent") not in INTENTS:
            continue
        intent = item["intent"]
        topic = item.get("topic")
        topic = topic if intent in TOPIC_INTENTS and topic in TOPICS and topic != "none" else None
        if (intent, topic) in seen:
            continue
        seen.add((intent, topic))
        resolved.append(ResolvedIntent(intent, LABELS[intent], topic))

    if not resolved:
        raise LlmBadResponse("쓸 수 있는 기능이 없습니다")
    # 응급이 하나라도 있으면 응급만 남긴다. unknown 은 다른 기능이 있으면 버린다.
    for r in resolved:
        if r.intent == "emergency":
            return [r]
    known = [r for r in resolved if r.intent != "unknown"]
    return (known or resolved)[:MAX_INTENTS]


class IntentClassifier:
    def __init__(self, settings: LlmSettings, client: httpx.AsyncClient) -> None:
        self.settings = settings
        self.client = client

    async def classify(self, text: str) -> list[ResolvedIntent]:
        last: Exception | None = None
        for ep in self.settings.endpoints:
            try:
                return await self._call(ep, text)
            except (httpx.HTTPError, LlmBadResponse) as err:
                last = err
                log.warning("LLM 호출 실패 model=%s (%s)", ep.model, type(err).__name__)
        raise LlmUnavailable("사용 가능한 LLM 서버가 없습니다") from last

    async def _call(self, ep: LlmEndpoint, text: str) -> list[ResolvedIntent]:
        body: dict[str, object] = {
            "model": ep.model,
            "temperature": 0,
            "max_tokens": 120,
            "messages": [{"role": "system", "content": PROMPT}, {"role": "user", "content": text}],
            "response_format": {"type": "json_schema", "json_schema": {"name": "intents", "strict": True, "schema": SCHEMA}},
        }
        # Qwen 계열은 기본이 "생각하는 모드"라 분류에는 끈다 (빠르고 형식이 안정적)
        if "qwen" in ep.model.lower():
            body["chat_template_kwargs"] = {"enable_thinking": False}
        headers = {"Authorization": f"Bearer {self.settings.api_key}"} if self.settings.api_key else {}
        res = await self.client.post(f"{ep.base_url}/chat/completions", json=body, headers=headers,
                                     timeout=self.settings.timeout_seconds)
        res.raise_for_status()
        try:
            content = res.json()["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as err:
            raise LlmBadResponse("응답 구조가 올바르지 않습니다") from err
        return normalize(content or "")
