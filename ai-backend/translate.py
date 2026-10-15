"""
외국어 처리 — 언어 판별(LLM 없음), Qwen3.6 호출(번역+검색어 확장, 답변 생성, 답변 언어 보정)
프롬프트 내용은 prompts.py에만 둔다.
"""

from __future__ import annotations

import logging
import re

import httpx

import config as C
import prompts as P
from rag import PipelineError

logger = logging.getLogger("global_chatbot.translate")

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)
# 답변 언어 검사 때 괄호 안 한국어 병기("Orthopedics (정형외과)")는 세지 않는다
_PARENS_RE = re.compile(r"[(（][^()（）]*[)）]")
_HANGUL_RE = re.compile(r"[가-힣]")
# 번체에만 쓰는 글자 (간체에서는 다른 글자). 병원 안내에 자주 나오는 글자 위주.
_TRADITIONAL_ONLY = set(
    "國醫診斷證書號門時費話點車開關館區廳樓層檢驗療藥習處當無麼們這說請從預約護雙電錢體會應術轉補後還進過讓圖華與為"
)
TRADITIONAL_MIN_CHARS = 2      # 이 개수 이상이면 번체 답변으로 본다
STRAY_HANGUL_MIN_CHARS = 2     # 괄호 밖 한글이 이 개수 이상이면 다시 쓰기


def detect_lang(text: str) -> str:
    """문자 종류로 언어를 판별한다 (LLM 호출 없음). 가장 많이 쓴 문자 계열로 결정."""
    counts = {"ko": 0, "zh": 0, "mn": 0, "en": 0}
    for ch in text:
        o = ord(ch)
        if 0xAC00 <= o <= 0xD7A3 or 0x3130 <= o <= 0x318F:
            counts["ko"] += 1
        elif 0x4E00 <= o <= 0x9FFF or 0x3400 <= o <= 0x4DBF:
            counts["zh"] += 1
        elif 0x0400 <= o <= 0x04FF:
            counts["mn"] += 1
        elif ch.isascii() and ch.isalpha():
            counts["en"] += 1
    best = max(counts, key=counts.get)
    return best if counts[best] > 0 else "unknown"


def answer_lang(text: str) -> str:
    """답변의 실제 언어 — 괄호 안 한국어 병기를 빼고 판별."""
    return detect_lang(_PARENS_RE.sub(" ", text))


def traditional_chars(text: str) -> int:
    """번체 전용 글자 수 (간체 답변이면 0이어야 함)."""
    return sum(1 for ch in text if ch in _TRADITIONAL_ONLY)


def stray_hangul(text: str) -> int:
    """괄호 밖에 남은 한글 글자 수 (외국어 답변이면 0이어야 함)."""
    return len(_HANGUL_RE.findall(_PARENS_RE.sub(" ", text)))


def answer_problems(lang: str, text: str) -> list[str]:
    """외국어 답변의 표기 문제 목록. 비어 있으면 통과."""
    problems = []
    got = answer_lang(text)
    if got != lang:
        problems.append(f"lang={got}")
    if lang == "zh" and traditional_chars(text) >= TRADITIONAL_MIN_CHARS:
        problems.append("traditional")
    if stray_hangul(text) >= STRAY_HANGUL_MIN_CHARS:
        problems.append("stray_hangul")
    return problems


_EMERGENCY_KO_RE = [re.compile(p) for p in P.EMERGENCY_PATTERNS_KO]


def has_emergency(*texts: str) -> bool:
    """응급 키워드(3개 언어) + 한국어 응급 표현 정규식(팀 화면과 같은 규칙). 외국어는 한국어 번역문도 함께 검사."""
    joined = " ".join(t.lower() for t in texts if t)
    if any(k.lower() in joined for k in P.EMERGENCY_KEYWORDS):
        return True
    return any(r.search(joined) for r in _EMERGENCY_KO_RE)


async def _chat(client: httpx.AsyncClient, messages: list[dict], *, max_tokens: int,
                temperature: float, stage: str, korean_model: bool = False) -> str:
    """korean_model=True면 한국어 답변용 카나나 (config.KO_LLM_*), 아니면 Qwen3.6."""
    if korean_model:
        base_url, model, key, timeout = C.KO_LLM_BASE_URL, C.KO_LLM_MODEL, C.KO_LLM_API_KEY, C.KO_LLM_TIMEOUT_SECONDS
    else:
        base_url, model, key, timeout = C.LLM_BASE_URL, C.LLM_MODEL, C.LLM_API_KEY, C.LLM_TIMEOUT_SECONDS
    body = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }
    if not korean_model:
        body["chat_template_kwargs"] = {"enable_thinking": False}   # Qwen3.x 추론 모드 끄기
    try:
        r = await client.post(
            f"{base_url}/chat/completions",
            headers={"Authorization": f"Bearer {key}"} if key else {},   # 키가 없으면 인증 헤더 생략
            json=body,
            timeout=timeout,
        )
        r.raise_for_status()
        msg = r.json()["choices"][0].get("message") or {}
    except httpx.HTTPError as e:
        raise PipelineError(stage, f"LLM 호출 실패: {type(e).__name__}") from e
    except (KeyError, IndexError, ValueError, TypeError) as e:
        raise PipelineError(stage, f"LLM 응답 파싱 실패: {type(e).__name__}") from e
    # vLLM + Qwen3.x: 답변이 reasoning 필드로 들어가는 경우 대비
    content = msg.get("content") or msg.get("reasoning_content") or msg.get("reasoning") or ""
    content = _THINK_RE.sub("", content).strip()
    if not content:
        raise PipelineError(stage, "LLM이 빈 답변을 반환")
    return content


async def translate_and_expand(client: httpx.AsyncClient, text: str) -> tuple[str, str]:
    """EXPAND_V1: 한 번의 호출로 (한국어 번역문, 검색 키워드)."""
    out = await _chat(client, P.expand_messages(text), max_tokens=200, temperature=0, stage="translate")
    ko, kw = "", ""
    for line in out.splitlines():
        s = line.strip()
        if s.upper().startswith("KO:"):
            ko = s[3:].strip()
        elif s.upper().startswith("KW:"):
            kw = s[3:].strip()
    if not ko:
        # 형식이 어긋나면 첫 줄을 번역문으로 쓴다 (키워드 없이 검색)
        ko = out.splitlines()[0].strip()
        logger.warning("확장 응답 형식 불일치 - 첫 줄을 번역문으로 사용")
    return ko, kw


async def answer(client: httpx.AsyncClient, lang: str, question: str, context: str) -> tuple[str, bool]:
    """ANSWER_V4로 답변 생성. 표기 문제(다른 언어·번체자·괄호 밖 한글)가 있으면 REWRITE_LANG_V2로 1회만 다시 쓴다.
    반환: (답변, 다시쓰기 했는지)"""
    text = await _chat(client, P.answer_messages(lang, question, context, C.INTL_CENTER_CONTACT),
                       max_tokens=C.LLM_ANSWER_MAX_TOKENS, temperature=0.3, stage="answer")
    problems = answer_problems(lang, text)
    if not problems:
        return text, False

    logger.warning("답변 표기 문제 (요청 %s: %s) - 1회 다시 쓰기", lang, ",".join(problems))
    fixed = await _chat(client, P.rewrite_messages(lang, text),
                        max_tokens=C.LLM_ANSWER_MAX_TOKENS, temperature=0, stage="rewrite")
    left = answer_problems(lang, fixed)
    if left:
        logger.warning("다시 쓰기 후에도 표기 문제 (요청 %s: %s) - 그대로 반환", lang, ",".join(left))
    return fixed, True


# 카나나 3B가 지시문을 답변에 옮겨 쓴 줄을 지우는 안전장치 (ANSWER_KO_V2와 함께)
_KO_PROMPT_LINE_RE = re.compile(r"참고 자료|3~5문장|답하세요|붙이세요|지어내지|OO")
_KO_LABEL_RE = re.compile(r"^\s*(\d+\.\s*)?(마지막 문장|관련 진료과|추천 의료진)\s*:\s*")


def clean_korean(text: str) -> str:
    """지시문 줄 삭제, "마지막 문장:" 같은 항목 이름 제거. 결과가 비면 원문 그대로."""
    lines = []
    seen_change_notice = False   # "변동될 수 있으니 확인" 안내는 한 번만 (2026-10-11 주차 답변에서 중복)
    for line in text.splitlines():
        if _KO_PROMPT_LINE_RE.search(line):
            continue
        if "변동될 수 있" in line:
            if seen_change_notice:
                continue
            seen_change_notice = True
        line = re.sub(r"^\s*마지막 문장\s*:\s*", "", line)
        lines.append(line)
    out = "\n".join(lines).strip()
    return out or text.strip()


async def answer_korean(client: httpx.AsyncClient, question: str, context: str, kind: str) -> str:
    """질문 종류(kind: symptom|general)별 ANSWER_KO_*_V3 + 카나나 3B → clean_korean()으로 지시문 흔적 정리."""
    text = await _chat(client, P.answer_ko_messages(question, context, kind, C.HOSPITAL_PHONE),
                       max_tokens=C.KO_LLM_ANSWER_MAX_TOKENS, temperature=0.3, stage="answer",
                       korean_model=True)
    return clean_korean(text)
