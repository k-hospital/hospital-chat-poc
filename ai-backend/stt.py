"""
음성인식 — 브라우저 녹음 파일을 받아 Whisper(speaches, OpenAI 호환)로 전달한다.
음성은 저장하지 않는다 (메모리에서 전달 후 폐기).
"""

from __future__ import annotations

import httpx

import config as C
from rag import PipelineError


async def transcribe(client: httpx.AsyncClient, audio: bytes, filename: str, content_type: str,
                     language: str | None) -> dict:
    """{text, language, duration} — language를 주면 감지 단계를 건너뛰어 더 빠르다."""
    data = {"model": C.STT_MODEL, "response_format": "verbose_json"}
    if language:
        data["language"] = language
    try:
        r = await client.post(
            C.STT_URL,
            data=data,
            files={"file": (filename or "audio.webm", audio, content_type or "application/octet-stream")},
            timeout=C.STT_TIMEOUT_SECONDS,
        )
        r.raise_for_status()
        j = r.json()
    except httpx.HTTPError as e:
        raise PipelineError("stt", f"Whisper 호출 실패: {type(e).__name__}") from e
    except ValueError as e:
        raise PipelineError("stt", "Whisper 응답 파싱 실패") from e
    return {
        "text": (j.get("text") or "").strip(),
        "language": (j.get("language") or language or "").lower() or None,
        "duration": j.get("duration"),
    }
