"""
답변 표기 회귀 테스트 — 프롬프트(prompts.py)를 바꿀 때마다 돌린다.

실행 중인 백엔드(/v1/chat/foreign)에 영어·중국어 질문을 보내고, 백엔드와 같은 기준(translate.answer_problems)으로
  - 답변 언어가 질문 언어인지 (괄호 안 한국어 병기 제외)
  - 중국어 답변에 번체자가 없는지
  - 괄호 밖에 한글이 남지 않았는지 (지명·역 이름 포함)
  - 중국어 병원 이름이 고정 명칭(国际圣母医院)인지
를 본다. 백엔드는 문제가 보이면 1회 다시 쓰므로, 여기서 실패 = 다시 쓰기 후에도 남은 문제.
서버 로그의 rewritten=True 건수로 다시 쓰기가 몇 번 작동했는지도 확인할 것.

실행:
    (백엔드) cd hospital-chat-poc\\ai-backend; $env:RATE_LIMIT_PER_MINUTE='0'; python -m uvicorn app:app --host 127.0.0.1 --port 8100
             ※ 테스트용으로만 요청 제한을 끈다 (기본 IP당 분당 20회라 --repeat 3이면 걸림). 운영 서버에는 쓰지 말 것
    (테스트) python check_answer_lang.py [--base http://127.0.0.1:8100] [--repeat 1] [--only 机场,airport]
    실패한 답변은 원문과 '괄호 밖 한글' 위치를 tests/results/answer_failures_<시각>.json 에 저장한다 (질문·답변만, 개인정보 없음).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime

import httpx

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from translate import answer_problems, stray_hangul, traditional_chars  # noqa: E402

CASES = [
    ("zh", "停车费是多少？"),          # V1에서 한국어로 답했던 질문
    ("zh", "我的手腕疼。"),
    ("zh", "睡眠内镜和普通内镜有什么区别？"),
    ("zh", "怎么开诊断书？"),          # V3에서 번체자로 답했던 질문
    ("zh", "从机场到医院怎么走？"),    # V3에서 역 이름에 한글이 남았던 질문
    ("en", "How much is the parking fee?"),
    ("en", "My wrist hurts."),
    ("en", "How do I get a medical certificate?"),
    ("en", "How do I get to the hospital from the airport?"),
]
ZH_HOSPITAL = "国际圣母医院"
ZH_OTHER_NAMES = ["圣玛丽", "圣玛利亚", "圣母玛利亚医院", "國際聖母醫院"]
RESULTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")
_PARENS = re.compile(r"[(（][^()（）]*[)）]")


def stray_contexts(text: str, width: int = 15) -> list[str]:
    """괄호 밖 한글 주변 문맥 (괄호 안은 같은 길이 공백으로 지워 위치를 유지) — 원인 확인용."""
    masked = _PARENS.sub(lambda m: " " * len(m.group()), text)
    out, last = [], -10**9
    for m in re.finditer(r"[가-힣]+", masked):
        if m.start() - last < width:      # 가까운 건 한 번만
            continue
        last = m.start()
        out.append(f"…{text[max(0, m.start() - width):m.end() + width]}…  [한글: {m.group()}]")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8100")
    ap.add_argument("--repeat", type=int, default=1, help="같은 질문 반복 횟수 (답변이 매번 조금씩 달라서)")
    ap.add_argument("--only", default=None, help="질문에 이 글자가 들어간 것만 실행 (예: 机场 / airport)")
    args = ap.parse_args()

    cases = [c for c in CASES if not args.only or any(k in c[1] for k in args.only.split(","))]
    client = httpx.Client(timeout=180)
    ok = total = name_bad = limited = 0
    times = []
    failures: list[dict] = []
    for rnd in range(1, args.repeat + 1):
        for lang, q in cases:
            t = time.perf_counter()
            r = client.post(f"{args.base}/v1/chat/foreign", json={"message": q, "lang": lang})
            dt = time.perf_counter() - t
            if r.status_code == 429:
                # 요청 제한은 프롬프트 결과가 아니므로 통과/실패 집계에서 뺀다
                limited += 1
                print(f"[{lang}] - 요청 제한(429) — 백엔드를 RATE_LIMIT_PER_MINUTE=0으로 띄웠는지 확인  {q}")
                continue
            times.append(dt)
            total += 1
            if r.status_code != 200:
                print(f"[{lang}] {q}  -> HTTP {r.status_code} {r.text[:120]}")
                continue
            ans = r.json()["answer"]
            problems = answer_problems(lang, ans)
            if lang == "zh" and any(n in ans for n in ZH_OTHER_NAMES):
                problems.append("hospital_name")
                name_bad += 1
            passed = not problems
            ok += passed
            name = " 병원명=고정명" if lang == "zh" and ZH_HOSPITAL in ans else ""
            print(f"[{lang}] {'O' if passed else 'X'} {dt:4.1f}s 번체={traditional_chars(ans) if lang == 'zh' else '-'} "
                  f"괄호밖한글={stray_hangul(ans)}{name} {('문제=' + ','.join(problems)) if problems else ''}  {q}")
            print("      " + ans[:170].replace("\n", " ") + ("…" if len(ans) > 170 else ""))
            if problems:
                ctx = stray_contexts(ans)
                for c in ctx:
                    print("      >> " + c.replace("\n", " "))
                failures.append({"round": rnd, "lang": lang, "question": q, "problems": problems,
                                 "stray_contexts": ctx, "answer": ans})
    if failures:
        os.makedirs(RESULTS_DIR, exist_ok=True)
        path = os.path.join(RESULTS_DIR, f"answer_failures_{datetime.now():%Y%m%d_%H%M%S}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(failures, f, ensure_ascii=False, indent=1)
        print(f"실패 답변 {len(failures)}건 저장: {path}")
    print("=" * 70)
    avg = f"평균 {sum(times) / len(times):.1f}s  최대 {max(times):.1f}s" if times else "응답 없음"
    print(f"통과 {ok}/{total}   중국어 병원명 다른 표기 {name_bad}건   요청 제한으로 미확인 {limited}건   {avg}")
    return 0 if ok == total and limited == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
