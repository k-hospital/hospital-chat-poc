"""질문 분류용 사내 LLM 연결 설정.

서버 주소와 모델 이름은 저장소(공개)에 두지 않고 실행하는 PC의 환경변수로만 받는다.
LLM_BASE_URL / LLM_MODEL 이 없으면 LLM 분류를 쓰지 않고(프론트는 키워드 규칙으로 동작) 경고만 남긴다.
"""
import logging
import os
from dataclasses import dataclass

log = logging.getLogger("chat.settings")

DEFAULT_TIMEOUT_SECONDS = 6.0
_OFF_VALUES = {"0", "false", "no", "off"}


@dataclass(frozen=True)
class LlmEndpoint:
    base_url: str  # OpenAI 호환 주소 (…/v1)
    model: str


@dataclass(frozen=True)
class LlmSettings:
    enabled: bool
    endpoints: tuple[LlmEndpoint, ...]  # 앞에서부터 시도하고, 실패하면 다음으로 넘어간다
    timeout_seconds: float


def _endpoint(url_var: str, model_var: str) -> LlmEndpoint | None:
    url = os.getenv(url_var, "").strip().rstrip("/")
    model = os.getenv(model_var, "").strip()
    return LlmEndpoint(url, model) if url and model else None


def load_settings() -> LlmSettings:
    endpoints = [e for e in (_endpoint("LLM_BASE_URL", "LLM_MODEL"),
                             _endpoint("LLM_FALLBACK_BASE_URL", "LLM_FALLBACK_MODEL")) if e]
    switched_on = os.getenv("LLM_ENABLED", "1").strip().lower() not in _OFF_VALUES
    if switched_on and not endpoints:
        log.warning("LLM_BASE_URL / LLM_MODEL 이 설정되지 않아 질문 분류(LLM)를 사용하지 않습니다")
    return LlmSettings(
        enabled=switched_on and bool(endpoints),
        endpoints=tuple(endpoints),
        timeout_seconds=float(os.getenv("LLM_TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT_SECONDS))),
    )
