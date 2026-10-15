"""
일반 안내 질문(주차·서류·검진 등) 적중률 측정 — 재청킹 후 기존 질문이 나빠지지 않았는지 확인용

리랭커 상위 5개 출처 제목에 기대 키워드가 하나라도 들어 있으면 적중.
한국어 질문만 사용 (현재 한국어 챗봇과 같은 조건). Qdrant는 읽기만 한다.

실행:
    python check_general_hit.py                                      # 운영 컬렉션
    $env:QDRANT_COLLECTION='hospital_chunks_test'; python check_general_hit.py
"""

from __future__ import annotations

import json
import os
import sys

import httpx
from qdrant_client import QdrantClient

from check_symptom_hit import search_titles
from check_translate_search import QDRANT_COLLECTION, QDRANT_URL

CASES_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "general_cases.json")


def compare_settings() -> int:
    """일반 안내 질문이 검색 설정 변경으로 나빠지지 않는지 확인.
    한국어 그대로(현재 한국어 챗봇)와 확장 경로(외국어 모듈과 같은 방식) 각각 4가지 설정."""
    from check_symptom_hit import SETTINGS, translate_and_expand
    with open(CASES_PATH, encoding="utf-8") as f:
        cases = json.load(f)
    http = httpx.Client(timeout=30)
    qdrant = QdrantClient(url=QDRANT_URL)
    score = {(p, s): 0 for p in ("그대로", "확장") for s in SETTINGS}
    for i, case in enumerate(cases, start=1):
        q0 = case["q"]
        ko, kw = translate_and_expand(http, q0)
        qx = f"{q0} {kw}".strip()
        marks = []
        for p, q in (("그대로", q0), ("확장", qx)):
            for s, (cand, use_kw) in SETTINGS.items():
                titles = search_titles(http, qdrant, q, q if use_kw else q0, candidates=cand)
                ok = any(k in t for t in titles for k in case["expect"])
                score[(p, s)] += ok
                marks.append("O" if ok else "X")
        print(f"[{i:2}] {q0:<24} 그대로 {' '.join(marks[:4])} | 확장 {' '.join(marks[4:])}")
    n = len(cases)
    print("=" * 70)
    print(f"일반 안내 설정 비교 ({n}건)  ※열 순서: " + ", ".join(SETTINGS))
    for p in ("그대로", "확장"):
        print(f"  {p:<4} " + "   ".join(f"{s}: {score[(p, s)]}/{n}" for s in SETTINGS))
    print("  (그대로 경로는 키워드가 없어 A=현재, A+B=B와 같은 조건)")
    return 0


def main() -> int:
    if "--compare-settings" in sys.argv:
        return compare_settings()
    with open(CASES_PATH, encoding="utf-8") as f:
        cases = json.load(f)
    http = httpx.Client(timeout=30)
    qdrant = QdrantClient(url=QDRANT_URL)

    print(f"컬렉션: {QDRANT_COLLECTION}")
    hits = 0
    for i, case in enumerate(cases, start=1):
        try:
            titles = search_titles(http, qdrant, case["q"], case["q"])
        except Exception as e:  # 점검 스크립트: 원인만 출력하고 중단
            print(f"[{i}] {case['q']} 실패: {type(e).__name__}: {e}")
            return 1
        ok = any(k in t for t in titles for k in case["expect"])
        hits += ok
        print(f"[{i:2}] {'O' if ok else 'X'}  {case['q']}")
        if not ok:
            print(f"       기대 {case['expect']} / 결과 {titles}")
    print(f"적중 {hits}/{len(cases)} ({hits / len(cases):.0%})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
