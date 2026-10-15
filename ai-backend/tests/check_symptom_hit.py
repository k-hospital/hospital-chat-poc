"""
증상 질문 → 기대 진료과 적중률 측정 (회귀 테스트용)

symptom_cases.json의 증상마다 아래 방식으로 검색하고,
리랭커 상위 5개 출처 제목에 기대 진료과가 들어 있으면 "적중"으로 센다.

  A    한국어 원문 그대로          (현재 한국어 챗봇과 동일)
  A+   한국어 + 질문 확장          (메인 챗봇에 확장을 넣으면 어떻게 되는지 참고용)
  C    외국어 → 번역만             (en, zh)
  D    외국어 → 번역 + 질문 확장   (en, zh, 설계안 후보)

적중 기준
  과   : 상위 5개 중 제목에 기대 진료과 이름이 있음
  의료진: 상위 5개 중 제목이 "<기대 진료과> > 의료진" 으로 시작함 (추천 의료진을 줄 수 있는지)

서버 호출만 하며 Qdrant는 읽기만 한다.

실행:
    python check_symptom_hit.py            # 요약 + 실패 사례만
    python check_symptom_hit.py --verbose  # 모든 사례의 상위 5개 제목과 확장 검색어
    python check_symptom_hit.py --compare-settings  # 후보 수(10/30)·리랭크 질문(KO/KO+KW) 4가지 설정 비교
"""

from __future__ import annotations

import json
import os
import sys
import time

import httpx
from qdrant_client import QdrantClient, models

from check_translate_search import (
    DENSE_VECTOR_NAME,
    HYBRID_SEARCH_LIMIT,
    QDRANT_COLLECTION,
    QDRANT_URL,
    QWEN_BASE_URL,
    QWEN_MODEL,
    RERANKER_URL,
    RERANK_TOP_N,
    SPARSE_VECTOR_NAME,
    dense,
    sparse,
    translate_to_korean,
)

CASES_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "symptom_cases.json")

EXPAND_PROMPT = """\
You prepare search queries for a Korean hospital information search engine.
The documents are written in Korean using hospital terminology
(e.g. 수부외과 for hand/wrist, 슬관절 for knee, 견관절 for shoulder, 족부 for foot/ankle).

For the user's question, output exactly two lines:
KO: <the question translated into natural Korean (if already Korean, copy it)>
KW: <5-8 Korean search keywords: relevant hospital department names as used in Korean hospitals,
     medical terms for the body part or symptom, separated by spaces>

Do not diagnose. Output only the two lines."""


def translate_and_expand(http: httpx.Client, text: str) -> tuple[str, str]:
    resp = http.post(
        f"{QWEN_BASE_URL}/chat/completions",
        json={
            "model": QWEN_MODEL,
            "messages": [
                {"role": "system", "content": EXPAND_PROMPT},
                {"role": "user", "content": text},
            ],
            "temperature": 0,
            "max_tokens": 200,
            "chat_template_kwargs": {"enable_thinking": False},
        },
        timeout=60,
    )
    resp.raise_for_status()
    message = resp.json()["choices"][0]["message"]
    content = (message.get("content") or message.get("reasoning_content") or "").strip()
    ko, kw = text, ""
    for line in content.splitlines():
        line = line.strip()
        if line.upper().startswith("KO:"):
            ko = line[3:].strip()
        elif line.upper().startswith("KW:"):
            kw = line[3:].strip()
    return ko, kw


def search_titles(http: httpx.Client, qdrant: QdrantClient, query: str, rerank_query: str,
                  candidates: int = HYBRID_SEARCH_LIMIT) -> list[str]:
    """하이브리드 검색(query, 후보 candidates개) + 리랭커(rerank_query) → 상위 제목 목록."""
    dv = dense(http, query)
    si, sv = sparse(http, query)
    points = qdrant.query_points(
        collection_name=QDRANT_COLLECTION,
        prefetch=[
            models.Prefetch(query=dv, using=DENSE_VECTOR_NAME, limit=candidates * 4),
            models.Prefetch(
                query=models.SparseVector(indices=si, values=sv),
                using=SPARSE_VECTOR_NAME,
                limit=candidates * 4,
            ),
        ],
        query=models.FusionQuery(fusion=models.Fusion.RRF),
        limit=candidates,
        with_payload=True,
    ).points
    if not points:
        return []
    texts = [(p.payload or {}).get("text") or (p.payload or {}).get("title") or "" for p in points]
    r = http.post(RERANKER_URL, json={"query": rerank_query, "texts": texts, "truncate": True})
    r.raise_for_status()
    ranked = sorted(r.json(), key=lambda x: x["score"], reverse=True)[:RERANK_TOP_N]
    return [(points[x["index"]].payload or {}).get("title") or "" for x in ranked]


def judge(titles: list[str], expect: list[str]) -> tuple[bool, bool]:
    dept_hit = any(d in t for t in titles for d in expect)
    doctor_hit = any(t.startswith(f"{d} > 의료진") for t in titles for d in expect)
    return dept_hit, doctor_hit


SETTINGS = {                 # 이름: (후보 수, 리랭크에 키워드 포함 여부)
    "현재(10,KO)": (10, False),
    "A(10,KO+KW)": (10, True),
    "B(30,KO)": (30, False),
    "A+B(30,KO+KW)": (30, True),
}


def compare_settings() -> int:
    """같은 확장 결과(KO/KW)로 검색 설정 4가지를 비교한다 (확장 결과가 같아야 공정한 비교).
    대상: A+(한국어+확장), D-en, D-zh. 의료진 적중은 '기대 진료과의 의료진 조각'이 있는지만 본다
    (맞는 세부 전문의인지는 trace_doctor_search.py로 따로 확인)."""
    with open(CASES_PATH, encoding="utf-8") as f:
        cases = json.load(f)
    http = httpx.Client(timeout=30)
    qdrant = QdrantClient(url=QDRANT_URL)
    paths = ["A+", "D-en", "D-zh"]
    score = {(p, s): [0, 0] for p in paths for s in SETTINGS}
    t_start = time.perf_counter()
    for i, case in enumerate(cases, start=1):
        line = []
        try:
            for p in paths:
                src = case["ko"] if p == "A+" else case[p[2:]]
                ko, kw = translate_and_expand(http, src)
                if p == "A+":
                    ko = case["ko"]
                q = f"{ko} {kw}".strip()
                for s, (cand, use_kw) in SETTINGS.items():
                    titles = search_titles(http, qdrant, q, q if use_kw else ko, candidates=cand)
                    d, doc = judge(titles, case["expect"])
                    score[(p, s)][0] += d
                    score[(p, s)][1] += doc
                    line.append(("O" if d else "X") + ("*" if doc else " "))
        except Exception as e:  # 점검 스크립트: 원인만 출력하고 중단
            print(f"[{i}] {case['ko']} 실패: {type(e).__name__}: {e}")
            return 1
        groups = [" ".join(line[k:k + len(SETTINGS)]) for k in range(0, len(line), len(SETTINGS))]
        print(f"[{i:2}] {case['ko']:<20} " + " | ".join(groups))
    n = len(cases)
    print("=" * 78)
    print(f"설정 비교 (상위 5개, {n}건)  각 칸: 진료과 / 의료진  ※열 순서: " + ", ".join(SETTINGS))
    for p in paths:
        cells = [f"{s}: {score[(p, s)][0]:2}/{score[(p, s)][1]:2}" for s in SETTINGS]
        print(f"  {p:<5} " + "   ".join(cells))
    print(f"소요 시간: {time.perf_counter() - t_start:.1f}s")
    return 0


def main() -> int:
    if "--compare-settings" in sys.argv:
        return compare_settings()
    verbose = "--verbose" in sys.argv
    with open(CASES_PATH, encoding="utf-8") as f:
        cases = json.load(f)

    http = httpx.Client(timeout=30)
    qdrant = QdrantClient(url=QDRANT_URL)

    modes = ["A", "A+", "C-en", "D-en", "C-zh", "D-zh"]
    score = {m: [0, 0] for m in modes}  # [과 적중, 의료진 적중]
    failures: list[str] = []
    t_start = time.perf_counter()

    for i, case in enumerate(cases, start=1):
        expect = case["expect"]
        runs: dict[str, tuple[str, list[str]]] = {}
        try:
            # 리랭커에는 확장 검색어를 붙이지 않은 질문(번역문)을 쓴다:
            # 키워드 나열이 리랭커 점수를 왜곡하지 않게 하고, 실제 서비스와 같은 조건으로 맞춤.
            runs["A"] = (case["ko"], search_titles(http, qdrant, case["ko"], case["ko"]))
            ko, kw = translate_and_expand(http, case["ko"])
            q = f"{case['ko']} {kw}".strip()
            runs["A+"] = (q, search_titles(http, qdrant, q, case["ko"]))
            for lang in ("en", "zh"):
                tr = translate_to_korean(http, case[lang])
                runs[f"C-{lang}"] = (tr, search_titles(http, qdrant, tr, tr))
                ko, kw = translate_and_expand(http, case[lang])
                q = f"{ko} {kw}".strip()
                runs[f"D-{lang}"] = (q, search_titles(http, qdrant, q, ko))
        except Exception as e:  # 점검 스크립트: 원인만 출력하고 중단
            print(f"[{i}] {case['ko']} 실패: {type(e).__name__}: {e}")
            return 1

        marks = []
        for m in modes:
            query, titles = runs[m]
            dept_hit, doctor_hit = judge(titles, expect)
            score[m][0] += dept_hit
            score[m][1] += doctor_hit
            marks.append(f"{m}:{'O' if dept_hit else 'X'}{'*' if doctor_hit else ' '}")
            if not dept_hit and m in ("D-en", "D-zh"):
                failures.append(f"  [{i}] {m} {case['ko']} → 기대 {expect}\n"
                                f"       검색어: {query}\n"
                                f"       결과: {titles}")
        print(f"[{i:2}] {case['ko']:<22} " + "  ".join(marks))
        if verbose:
            for m in modes:
                query, titles = runs[m]
                print(f"      {m:<5} {query}")
                for t in titles:
                    print(f"            - {t}")

    n = len(cases)
    print("=" * 70)
    print(f"적중률 (상위 5개 기준, {n}건)   O=진료과 적중, *=해당 과 의료진 조각까지 적중")
    for m in modes:
        d, doc = score[m]
        print(f"  {m:<5} 진료과 {d:2}/{n} ({d / n:4.0%})   의료진 {doc:2}/{n} ({doc / n:4.0%})")
    print(f"소요 시간: {time.perf_counter() - t_start:.1f}s")
    if failures:
        print("=" * 70)
        print("D(설계안 후보) 실패 사례")
        print("\n".join(failures))
    return 0


if __name__ == "__main__":
    sys.exit(main())
