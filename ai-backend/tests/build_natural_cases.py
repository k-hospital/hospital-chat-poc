"""
실제 환자식 한국어 질문 만들기 — faq_cases.json의 '페이지 제목으로 만든 쉬운 질문'을 Qwen3.6으로
환자가 챗봇에 실제로 칠 법한 구어체 질문으로 바꾼다. 정답(urls·code)은 원래 것을 그대로 쓴다.

출력: faq_cases_natural.json  (각 항목에 원래 질문 orig 포함)
주의: LLM이 바꾼 질문이라 실제 환자 말투와 다를 수 있다. 직접 쓴 질문을 같은 형식으로 추가해도 된다.

실행: python build_natural_cases.py
"""

from __future__ import annotations

import json
import os
import sys
import time

import httpx

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "faq_cases.json")
OUT = os.path.join(HERE, "faq_cases_natural.json")
try:  # 사내 서버 주소·모델 이름은 ai-backend/.env 에서 읽는다 (저장소에 적지 않음)
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env"))
except ImportError:
    pass

LLM_URL = os.environ.get("LLM_BASE_URL", "").rstrip("/") + "/chat/completions"
LLM_MODEL = os.environ.get("LLM_MODEL", "")

PROMPT = """\
다음은 병원 홈페이지 제목으로 자동으로 만든 질문입니다.
이 질문을 실제 환자나 보호자가 병원 안내 챗봇에 입력할 법한 자연스러운 한국어 질문 1개로 바꾸세요.

규칙:
- 구어체, 짧게 (예: "~요?", "~나요?", "~있어요?"). 사정이나 상황을 한 마디 붙여도 좋음
- 페이지 제목을 그대로 베끼지 말고 환자가 쓸 법한 말로 바꿀 것
- 단, 무엇을 묻는지는 알아볼 수 있게 남길 것 (진료과·검사·항목·장비·장소 이름의 핵심 단어는 유지하거나 흔한 말로)
- 비급여 비용 질문은 "얼마예요", "비용이 어떻게 돼요" 같은 표현으로
- 질문 한 줄만 출력 (따옴표·설명 없이)"""


def main() -> int:
    cases = json.load(open(SRC, encoding="utf-8"))
    client = httpx.Client(timeout=60)
    out = []
    t0 = time.perf_counter()
    for i, c in enumerate(cases, start=1):
        try:
            r = client.post(LLM_URL, json={
                "model": LLM_MODEL,
                "messages": [{"role": "system", "content": PROMPT},
                             {"role": "user", "content": f"원래 질문: {c['q']}\n분류: {c['category']}"}],
                "temperature": 0.7, "max_tokens": 80,
                "chat_template_kwargs": {"enable_thinking": False},
            })
            r.raise_for_status()
            msg = r.json()["choices"][0]["message"]
            q = (msg.get("content") or msg.get("reasoning_content") or "").strip().splitlines()[0].strip(" \"'")
        except Exception as e:  # 원인만 보고하고 중단 (재시도 안 함)
            print(f"[{i}] 실패: {type(e).__name__}: {e}")
            return 1
        out.append({**c, "orig": c["q"], "q": q or c["q"]})
        if i % 50 == 0:
            print(f"{i}/{len(cases)} ({time.perf_counter() - t0:.0f}s)")
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"저장: {OUT} ({len(out)}건, {time.perf_counter() - t0:.0f}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
