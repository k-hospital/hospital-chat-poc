"""
검색 파이프라인 — hospital_chatbot_poc/main.py의 검색 부분을 복사해 이 모듈에 맞게 정리.
(main.py를 메인 담당자가 바꿔도 영향받지 않도록 복사본을 쓴다. 검색 방식이 바뀌면 양쪽을 맞출 것)

  dense(bge-m3) + sparse(bge-m3 sparse) -> Qdrant 하이브리드(RRF) -> 리랭커 상위 N
"""

from __future__ import annotations

from typing import Any

import httpx
from qdrant_client import AsyncQdrantClient, models

import config as C


class PipelineError(Exception):
    """어느 단계에서 실패했는지 남기기 위한 예외 (사용자에게는 오류 코드만 보낸다)."""

    def __init__(self, stage: str, detail: str):
        self.stage = stage
        self.detail = detail
        super().__init__(f"[{stage}] {detail}")


async def dense_embedding(client: httpx.AsyncClient, text: str) -> list[float]:
    try:
        r = await client.post(C.DENSE_EMBEDDING_URL, json={"model": C.DENSE_EMBEDDING_MODEL, "input": text})
        r.raise_for_status()
        return r.json()["data"][0]["embedding"]
    except httpx.HTTPError as e:
        raise PipelineError("dense", f"호출 실패: {type(e).__name__}") from e
    except (KeyError, IndexError, ValueError) as e:
        raise PipelineError("dense", f"응답 파싱 실패: {type(e).__name__}") from e


def _parse_sparse(data: Any) -> tuple[list[int], list[float]]:
    if isinstance(data, list) and data and isinstance(data[0], list):
        data = data[0]
    if isinstance(data, dict) and "indices" in data:
        return list(data["indices"]), [float(v) for v in data["values"]]
    if isinstance(data, list):
        return [int(x["index"]) for x in data], [float(x["value"]) for x in data]
    raise ValueError("알 수 없는 sparse 응답 형식")


async def sparse_embedding(client: httpx.AsyncClient, text: str) -> tuple[list[int], list[float]]:
    try:
        r = await client.post(C.SPARSE_EMBEDDING_URL, json={"inputs": text})
        r.raise_for_status()
        return _parse_sparse(r.json())
    except httpx.HTTPError as e:
        raise PipelineError("sparse", f"호출 실패: {type(e).__name__}") from e
    except (KeyError, ValueError, TypeError) as e:
        raise PipelineError("sparse", f"응답 파싱 실패: {type(e).__name__}") from e


async def hybrid_search(qdrant: AsyncQdrantClient, dense: list[float], s_idx: list[int],
                        s_val: list[float]) -> list[models.ScoredPoint]:
    limit = C.HYBRID_SEARCH_LIMIT
    try:
        result = await qdrant.query_points(
            collection_name=C.QDRANT_COLLECTION,
            prefetch=[
                models.Prefetch(query=dense, using=C.DENSE_VECTOR_NAME, limit=limit * 4),
                models.Prefetch(query=models.SparseVector(indices=s_idx, values=s_val),
                                using=C.SPARSE_VECTOR_NAME, limit=limit * 4),
            ],
            query=models.FusionQuery(fusion=models.Fusion.RRF),
            limit=limit,
            with_payload=True,
        )
        return result.points
    except Exception as e:  # qdrant_client는 다양한 예외를 던진다
        raise PipelineError("qdrant", f"검색 실패: {type(e).__name__}") from e


def payload_text(payload: dict) -> str:
    return payload.get("text") or payload.get("title") or ""


async def rerank(client: httpx.AsyncClient, query: str,
                 points: list[models.ScoredPoint]) -> list[models.ScoredPoint]:
    if len(points) <= 1:
        return points
    try:
        r = await client.post(C.RERANKER_URL, json={
            "query": query, "texts": [payload_text(p.payload or {}) for p in points], "truncate": True})
        r.raise_for_status()
        ranked = sorted(r.json(), key=lambda x: x["score"], reverse=True)[: C.RERANK_TOP_N]
        picked = []
        for item in ranked:
            p = points[item["index"]]
            p.score = float(item["score"])
            picked.append(p)
        return picked
    except httpx.HTTPError as e:
        raise PipelineError("reranker", f"호출 실패: {type(e).__name__}") from e
    except (KeyError, IndexError, ValueError, TypeError) as e:
        raise PipelineError("reranker", f"응답 파싱 실패: {type(e).__name__}") from e


async def search(client: httpx.AsyncClient, qdrant: AsyncQdrantClient,
                 query: str, rerank_query: str) -> list[models.ScoredPoint]:
    """query(번역문 + 확장 키워드)로 검색하고, rerank_query로 순위를 다시 매긴다
    (기본: 번역문+키워드 — config.RERANK_WITH_KEYWORDS)."""
    dense = await dense_embedding(client, query)
    s_idx, s_val = await sparse_embedding(client, query)
    candidates = await hybrid_search(qdrant, dense, s_idx, s_val)
    return await rerank(client, rerank_query, candidates)


def build_context(points: list[models.ScoredPoint], max_chunk: int | None = None,
                  max_context: int | None = None, korean: bool = False) -> str:
    """리랭커 순서대로 담다가 전체 한도를 넘으면 멈춘다 (최소 1개는 포함).
    한도를 안 주면 외국어(Qwen3.6)용 기본값. korean=True면 한국어 머리말 (카나나용)."""
    max_chunk = max_chunk or C.MAX_CHUNK_CHARS
    max_context = max_context or C.MAX_CONTEXT_CHARS
    if not points:
        return "(참고 자료 없음)" if korean else "(no reference found)"
    blocks: list[str] = []
    total = 0
    for i, p in enumerate(points, start=1):
        payload = p.payload or {}
        text = payload_text(payload)
        if len(text) > max_chunk:
            text = text[: max_chunk] + " …"
        if korean:
            block = f"[참고 {i}] (분류: {payload.get('category', '')})\n{text}"
        else:
            block = f"[Reference {i}] (category: {payload.get('category', '')})\n{text}"
        if blocks and total + len(block) > max_context:
            break
        blocks.append(block)
        total += len(block)
    return "\n\n".join(blocks)


def sources_of(points: list[models.ScoredPoint]) -> list[dict]:
    """출처 카드용. 같은 페이지는 한 번만."""
    out, seen = [], set()
    for p in points:
        pl = p.payload or {}
        key = (pl.get("title"), pl.get("source_url"))
        if key in seen:
            continue
        seen.add(key)
        # 제목이 빈 조각이 있으면 분류명 → URL 순으로 대신 표시 (출처 카드가 빈칸이 되지 않게)
        title = (pl.get("title") or "").strip() or (pl.get("category") or "").strip() or pl.get("source_url") or "-"
        out.append({"title": title, "category": pl.get("category"),
                    "source_url": pl.get("source_url"), "score": p.score})
    return out
