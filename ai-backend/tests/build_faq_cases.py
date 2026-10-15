"""
한국어 검색 정확도 테스트 질문 만들기 — 홈페이지 크롤링/faq.jsonl(질문 + 정답 페이지, 1,288쌍)에서 뽑는다.

  - 비급여(nonpayment) 1,067건은 "○○ 비급여 비용이 얼마예요?" 틀이 반복되므로 100건만 무작위(seed 0)
  - 나머지 카테고리(guide·department·center·equipment·hospital_intro)는 전부
  - 같은 질문이 여러 페이지에 있으면 1건으로 합치고 정답 URL을 모두 허용
  - 비급여는 URL이 전부 같아서, 답에 적힌 항목 코드 "(C5841)"를 정답 판정용으로 저장

출력: faq_cases.json  [{q, category, urls[], section, code}]
주의: faq.jsonl의 질문은 페이지 제목으로 자동 생성한 문장이라 실제 환자 질문보다 쉬울 수 있다 (기본기 점검용).

실행: python build_faq_cases.py
"""

from __future__ import annotations

import json
import os
import random
import re
from collections import Counter, OrderedDict

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "..", "data", "홈페이지 크롤링", "faq.jsonl")
OUT = os.path.join(HERE, "faq_cases.json")
NONPAYMENT_SAMPLE = 100
_CODE_RE = re.compile(r"\(([A-Z0-9]{4,})\)")


def main() -> None:
    rows = [json.loads(line) for line in open(SRC, encoding="utf-8") if line.strip()]
    nonpay = [r for r in rows if r["category"] == "nonpayment"]
    others = [r for r in rows if r["category"] != "nonpayment"]
    random.Random(0).shuffle(nonpay)

    cases: "OrderedDict[str, dict]" = OrderedDict()
    for r in others:
        c = cases.setdefault(r["question"], {"q": r["question"], "category": r["category"], "urls": [],
                                             "section": r.get("section") or "", "code": ""})
        if r["url"] not in c["urls"]:
            c["urls"].append(r["url"])

    picked = 0
    for r in nonpay:
        if picked >= NONPAYMENT_SAMPLE:
            break
        m = _CODE_RE.search(r["answer"])
        if not m or r["question"] in cases:
            continue
        cases[r["question"]] = {"q": r["question"], "category": "nonpayment", "urls": [r["url"]],
                                "section": "", "code": m.group(1)}
        picked += 1

    out = list(cases.values())
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"테스트 질문 {len(out)}건 저장: {OUT}")
    print("카테고리별:", dict(Counter(c["category"] for c in out)))


if __name__ == "__main__":
    main()
