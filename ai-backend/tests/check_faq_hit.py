"""
한국어 검색 정확도 측정 — faq_cases.json(build_faq_cases.py)의 질문을 '한국어 그대로'(키워드 확장 없음) 검색해서
정답이 상위 1·3·5개 안에 드는지 카테고리별로 본다. LLM 호출 없음, Qdrant는 읽기만.

판정
  - 일반 카테고리: 정답 URL의 조각이 들어 있으면 '페이지 적중', 그 조각 제목에 섹션명까지 있으면 '섹션 적중'
  - nonpayment   : 조각 본문에 정답 항목 코드(예: C5841)가 있으면 적중 (비급여 조각은 URL이 전부 같아서)

검색 경로 (외국어 모듈과 같은 함수, 번역·키워드만 없음)
  dense+sparse → RRF 후보 N개 → 리랭커(질문 그대로) → 상위 5

실행:
    python check_faq_hit.py                     # 후보 10과 30 두 설정 비교
    python check_faq_hit.py --candidates 30     # 한 설정만
    python check_faq_hit.py --show-fail 20      # 실패 사례 20건 출력
    $env:QDRANT_COLLECTION='hospital_chunks_test'; python check_faq_hit.py   # 테스트 컬렉션
결과 파일: results/faq_hit_<시각>.json (실패 사례 포함)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import defaultdict
from datetime import datetime

import httpx
from qdrant_client import QdrantClient, models

from check_translate_search import (DENSE_VECTOR_NAME, QDRANT_COLLECTION, QDRANT_URL, RERANKER_URL,
                                    SPARSE_VECTOR_NAME, dense, sparse)

HERE = os.path.dirname(os.path.abspath(__file__))
CASES = os.path.join(HERE, "faq_cases.json")
TOP_K = 5


def search(http: httpx.Client, qdrant: QdrantClient, q: str, candidates: int) -> list[dict]:
    dv = dense(http, q)
    si, sv = sparse(http, q)
    pts = qdrant.query_points(
        collection_name=QDRANT_COLLECTION,
        prefetch=[models.Prefetch(query=dv, using=DENSE_VECTOR_NAME, limit=candidates * 4),
                  models.Prefetch(query=models.SparseVector(indices=si, values=sv),
                                  using=SPARSE_VECTOR_NAME, limit=candidates * 4)],
        query=models.FusionQuery(fusion=models.Fusion.RRF), limit=candidates, with_payload=True).points
    if not pts:
        return []
    texts = [(p.payload or {}).get("text") or "" for p in pts]
    r = http.post(RERANKER_URL, json={"query": q, "texts": texts, "truncate": True})
    r.raise_for_status()
    ranked = sorted(r.json(), key=lambda x: x["score"], reverse=True)[:TOP_K]
    return [pts[x["index"]].payload or {} for x in ranked]


def rank(case: dict, payloads: list[dict]) -> tuple[int, int]:
    """(페이지·코드 적중 순위, 섹션 적중 순위). 없으면 0."""
    page = sec = 0
    for i, p in enumerate(payloads, start=1):
        if case["category"] == "nonpayment":
            ok = case["code"] and case["code"] in (p.get("text") or "")
            if ok and not page:
                page = sec = i
            continue
        if p.get("source_url") in case["urls"]:
            page = page or i
            if not sec and (not case["section"] or case["section"] in (p.get("title") or "")):
                sec = i
    return page, sec


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidates", type=int, default=0, help="후보 수 하나만 (기본: 10과 30 비교)")
    ap.add_argument("--show-fail", type=int, default=15, help="출력할 실패 사례 수")
    ap.add_argument("--cases", default=CASES, help="질문 파일 (기본 faq_cases.json, 환자식은 faq_cases_natural.json)")
    args = ap.parse_args()
    settings = [args.candidates] if args.candidates else [10, 30]

    cases = json.load(open(args.cases, encoding="utf-8"))
    print(f"질문 파일: {os.path.basename(args.cases)}")
    http = httpx.Client(timeout=60)
    qdrant = QdrantClient(url=QDRANT_URL)
    print(f"컬렉션 {QDRANT_COLLECTION}, 질문 {len(cases)}건, 설정(후보 수) {settings}")

    report = {"collection": QDRANT_COLLECTION, "cases": os.path.basename(args.cases),
              "time": datetime.now().isoformat(timespec="seconds"), "settings": {}}
    for cand in settings:
        t0 = time.perf_counter()
        stat = defaultdict(lambda: [0, 0, 0, 0, 0])   # n, hit@1, hit@3, hit@5, 섹션@5
        fails = []
        for i, c in enumerate(cases, start=1):
            try:
                payloads = search(http, qdrant, c["q"], cand)
            except Exception as e:  # 원인만 보고하고 중단 (재시도 안 함)
                print(f"[{i}] 실패: {type(e).__name__}: {e}")
                return 1
            page, sec = rank(c, payloads)
            for key in (c["category"], "전체"):
                s = stat[key]
                s[0] += 1
                s[1] += page == 1
                s[2] += 0 < page <= 3
                s[3] += page > 0
                s[4] += sec > 0
            if not page:
                fails.append({"q": c["q"], "orig": c.get("orig", ""), "category": c["category"],
                              "want": c["code"] or c["urls"],
                              "got": [p.get("title") for p in payloads]})
        print("=" * 72)
        print(f"후보 {cand}개  ({time.perf_counter() - t0:.0f}s)")
        print(f"  {'카테고리':<15}{'건수':>5}{'@1':>8}{'@3':>8}{'@5':>8}{'섹션@5':>9}")
        cats = sorted(k for k in stat if k != "전체") + ["전체"]
        for k in cats:
            n, h1, h3, h5, s5 = stat[k]
            sec = "-" if k == "nonpayment" else f"{s5 / n:.0%}"
            print(f"  {k:<15}{n:>5}{h1 / n:>8.0%}{h3 / n:>8.0%}{h5 / n:>8.0%}{sec:>9}")
        report["settings"][str(cand)] = {"stat": {k: stat[k] for k in cats}, "fails": fails}
        for f in fails[: args.show_fail]:
            orig = f"  (원래: {f['orig']})" if f["orig"] else ""
            print(f"  X [{f['category']}] {f['q']}{orig}\n      정답 {f['want']}  /  결과 {f['got']}")

    os.makedirs(os.path.join(HERE, "results"), exist_ok=True)
    path = os.path.join(HERE, "results", f"faq_hit_{datetime.now():%Y%m%d_%H%M%S}.json")
    json.dump(report, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"결과 저장: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
