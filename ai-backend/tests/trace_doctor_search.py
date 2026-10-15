"""
증상 질문 검색 진단 — 맞는 전문의 조각이 검색의 어느 단계에서 빠지는지 순위로 추적한다.

  ① 번역+키워드 (EXPAND_V1)         → KO / KW
  ② dense 단독 상위 40 안 순위
  ③ sparse 단독 상위 40 안 순위
  ④ 하이브리드(RRF) 후보 안 순위      — 현재 후보 수 10, 비교용 30
  ⑤ 리랭커 순위                       — 현재: 번역문(KO)으로 / 비교: KO+KW로
     (현재 운영: 후보 10 → 리랭커(KO) → 상위 5)

Qdrant·임베딩·리랭커·Qwen은 읽기만 한다. 백엔드(hospital-chat-poc/ai-backend)의 설정·함수를 그대로 쓴다.

실행:
    python trace_doctor_search.py                                  # "My wrist hurts." 5회, 대상 김상희
    python trace_doctor_search.py --query "손목이 아파요" --korean  # 한국어 그대로(확장 없음, 한국어 챗봇 조건)
    python trace_doctor_search.py --query "My knee hurts." --target 전병훈
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

import httpx
from qdrant_client import AsyncQdrantClient, models

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import config as C  # noqa: E402
import rag  # noqa: E402
import translate as T  # noqa: E402


def rank_of(points, target: str) -> str:
    for i, p in enumerate(points, start=1):
        if target in rag.payload_text(p.payload or {}):
            return str(i)
    return "-"


async def single(qdrant, using: str, query, limit: int):
    r = await qdrant.query_points(C.QDRANT_COLLECTION, query=query, using=using, limit=limit, with_payload=True)
    return r.points


async def hybrid(qdrant, dense, sp, limit: int):
    r = await qdrant.query_points(
        C.QDRANT_COLLECTION,
        prefetch=[models.Prefetch(query=dense, using=C.DENSE_VECTOR_NAME, limit=limit * 4),
                  models.Prefetch(query=sp, using=C.SPARSE_VECTOR_NAME, limit=limit * 4)],
        query=models.FusionQuery(fusion=models.Fusion.RRF), limit=limit, with_payload=True)
    return r.points


async def rerank_all(client, query: str, points):
    """리랭커로 전체 후보를 정렬 (상위 N 자르지 않음)."""
    if not points:
        return []
    r = await client.post(C.RERANKER_URL, json={
        "query": query, "texts": [rag.payload_text(p.payload or {}) for p in points], "truncate": True})
    r.raise_for_status()
    ranked = sorted(r.json(), key=lambda x: x["score"], reverse=True)
    return [(points[x["index"]], float(x["score"])) for x in ranked]


def short_titles(pairs, n=5):
    out = []
    for p, s in pairs[:n]:
        t = rag.payload_text(p.payload or {}).splitlines()
        who = next((ln for ln in t if "교수" in ln), (p.payload or {}).get("title", ""))
        out.append(f"{s:.3f} {who[:28]}")
    return out


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--query", default="My wrist hurts.")
    ap.add_argument("--target", default="김상희", help="찾아야 할 전문의 이름 (조각 본문에 들어 있는 글자)")
    ap.add_argument("--repeat", type=int, default=5)
    ap.add_argument("--korean", action="store_true", help="번역·확장 없이 질문 그대로 (한국어 챗봇 조건)")
    args = ap.parse_args()

    client = httpx.AsyncClient(timeout=60)
    qdrant = AsyncQdrantClient(url=C.QDRANT_URL)
    print(f"질문: {args.query}  /  대상: {args.target}  /  컬렉션: {C.QDRANT_COLLECTION}")
    print("순위 '-' = 그 단계 목록 안에 없음.  현재 운영 경로 = 후보10 → 리랭커(KO) → 상위5")
    print("=" * 78)
    header = f"{'회':>2} {'dense40':>7} {'sparse40':>8} {'후보10':>6} {'후보30':>6} | " \
             f"{'리랭크10(KO)':>11} {'리랭크10(KO+KW)':>14} {'리랭크30(KO)':>11} {'리랭크30(KO+KW)':>14}"
    print(header)
    runs = 1 if args.korean else args.repeat
    for i in range(1, runs + 1):
        if args.korean:
            ko, kw = args.query, ""
        else:
            ko, kw = await T.translate_and_expand(client, args.query)
        q = f"{ko} {kw}".strip()
        dense = await rag.dense_embedding(client, q)
        idx, val = await rag.sparse_embedding(client, q)
        sp = models.SparseVector(indices=idx, values=val)

        d40 = await single(qdrant, C.DENSE_VECTOR_NAME, dense, 40)
        s40 = await single(qdrant, C.SPARSE_VECTOR_NAME, sp, 40)
        h10 = await hybrid(qdrant, dense, sp, 10)
        h30 = await hybrid(qdrant, dense, sp, 30)
        r10_ko = await rerank_all(client, ko, h10)
        r10_kw = await rerank_all(client, q, h10)
        r30_ko = await rerank_all(client, ko, h30)
        r30_kw = await rerank_all(client, q, h30)

        def rr(pairs):
            return rank_of([p for p, _ in pairs], args.target)

        print(f"{i:>2} {rank_of(d40, args.target):>7} {rank_of(s40, args.target):>8} {rank_of(h10, args.target):>6} "
              f"{rank_of(h30, args.target):>6} | {rr(r10_ko):>11} {rr(r10_kw):>14} {rr(r30_ko):>11} {rr(r30_kw):>14}")
        print(f"   KO: {ko}   KW: {kw}")
        print(f"   현재 상위5(리랭크10·KO): {short_titles(r10_ko)}")
        if i == runs:
            print(f"   비교 상위5(리랭크30·KO+KW): {short_titles(r30_kw)}")
    await client.aclose()
    await qdrant.close()


if __name__ == "__main__":
    asyncio.run(main())
