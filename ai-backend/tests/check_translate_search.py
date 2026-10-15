"""
0단계 사전 점검: 외국어 질문 → 한국어 번역 → 기존 RAG 검색 품질 확인

확인 내용
  1) Qwen3.6 35B 서버 응답 (/v1/models)
  2) 질문별로 세 가지 검색 결과(리랭커 상위 5) 비교
       A. 한국어 기준 질문   (정답 기준)
       B. 외국어 원문 그대로 (번역 없이 교차언어 검색)
       C. 외국어 → Qwen3.6 한국어 번역 후 검색 (설계안)
     B·C가 A와 몇 개 겹치는지 출력
  3) 단계별 소요 시간

서버 호출만 하며, Qdrant 데이터는 읽기만 한다 (쓰기 없음).

실행:
    cd D:\\AI_STUDY\\10_Work\\병원챗봇\\hospital_chatbot\\tests
    python check_translate_search.py
"""

from __future__ import annotations

import os
import sys
import time

import httpx
from qdrant_client import QdrantClient, models

# 설정은 hospital_chatbot_poc/main.py와 같은 환경변수 이름·기본값을 사용
try:  # 사내 서버 주소·모델 이름은 ai-backend/.env 에서 읽는다 (저장소에 적지 않음)
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env"))
except ImportError:
    pass

QDRANT_URL = os.environ.get("QDRANT_URL", "")
QDRANT_COLLECTION = os.environ.get("QDRANT_COLLECTION", "hospital_chunks")
DENSE_VECTOR_NAME = os.environ.get("DENSE_VECTOR_NAME", "text-dense")
SPARSE_VECTOR_NAME = os.environ.get("SPARSE_VECTOR_NAME", "text-sparse")
DENSE_EMBEDDING_URL = os.environ.get(
    "DENSE_EMBEDDING_URL", ""
)
DENSE_EMBEDDING_MODEL = os.environ.get("DENSE_EMBEDDING_MODEL", "BAAI/bge-m3")
SPARSE_EMBEDDING_URL = os.environ.get(
    "SPARSE_EMBEDDING_URL", ""
)
RERANKER_URL = os.environ.get("RERANKER_URL", "")

# 외국어용 LLM: Qwen3.6 35B
QWEN_BASE_URL = os.environ.get("QWEN_BASE_URL", "")
QWEN_MODEL = os.environ.get("QWEN_MODEL", "")

HYBRID_SEARCH_LIMIT = 10
RERANK_TOP_N = 5

# (언어, 외국어 질문, 한국어 기준 질문)
TEST_CASES = [
    ("en", "My wrist hurts.", "손목이 아파요"),
    ("en", "How much is the parking fee?", "주차 요금이 어떻게 되나요?"),
    ("en", "What is the difference between sleep endoscopy and regular endoscopy?",
     "수면내시경은 일반내시경이랑 뭐가 달라요?"),
    ("zh", "我的手腕疼。", "손목이 아파요"),
    ("zh", "停车费是多少？", "주차 요금이 어떻게 되나요?"),
    ("zh", "睡眠内镜和普通内镜有什么区别？", "수면내시경은 일반내시경이랑 뭐가 달라요?"),
]

TRANSLATE_PROMPT = """\
You translate patient questions for a Korean hospital information search.
Translate the user's question into natural Korean.
Use the everyday Korean terms used in Korean hospitals for symptoms, body parts, and departments.
Output only the Korean translation. No explanations, no quotes."""


def translate_to_korean(http: httpx.Client, text: str) -> str:
    resp = http.post(
        f"{QWEN_BASE_URL}/chat/completions",
        json={
            "model": QWEN_MODEL,
            "messages": [
                {"role": "system", "content": TRANSLATE_PROMPT},
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
    content = message.get("content") or message.get("reasoning_content") or ""
    return content.strip()


def dense(http: httpx.Client, text: str) -> list[float]:
    r = http.post(DENSE_EMBEDDING_URL, json={"model": DENSE_EMBEDDING_MODEL, "input": text})
    r.raise_for_status()
    return r.json()["data"][0]["embedding"]


def sparse(http: httpx.Client, text: str) -> tuple[list[int], list[float]]:
    r = http.post(SPARSE_EMBEDDING_URL, json={"inputs": text})
    r.raise_for_status()
    data = r.json()
    if isinstance(data, list) and data and isinstance(data[0], list):
        data = data[0]
    return [int(x["index"]) for x in data], [float(x["value"]) for x in data]


def search(http: httpx.Client, qdrant: QdrantClient, query: str) -> list[tuple[str, float]]:
    """하이브리드 검색 + 리랭커 → [(제목, 리랭커 점수)] 상위 RERANK_TOP_N."""
    dv = dense(http, query)
    si, sv = sparse(http, query)
    points = qdrant.query_points(
        collection_name=QDRANT_COLLECTION,
        prefetch=[
            models.Prefetch(query=dv, using=DENSE_VECTOR_NAME, limit=HYBRID_SEARCH_LIMIT * 4),
            models.Prefetch(
                query=models.SparseVector(indices=si, values=sv),
                using=SPARSE_VECTOR_NAME,
                limit=HYBRID_SEARCH_LIMIT * 4,
            ),
        ],
        query=models.FusionQuery(fusion=models.Fusion.RRF),
        limit=HYBRID_SEARCH_LIMIT,
        with_payload=True,
    ).points
    if not points:
        return []
    texts = [(p.payload or {}).get("text") or (p.payload or {}).get("title") or "" for p in points]
    r = http.post(RERANKER_URL, json={"query": query, "texts": texts, "truncate": True})
    r.raise_for_status()
    ranked = sorted(r.json(), key=lambda x: x["score"], reverse=True)[:RERANK_TOP_N]
    return [((points[x["index"]].payload or {}).get("title") or "(제목 없음)", float(x["score"]))
            for x in ranked]


def print_results(label: str, results: list[tuple[str, float]], baseline: set[str] | None) -> None:
    overlap = ""
    if baseline is not None:
        n = len({t for t, _ in results} & baseline)
        overlap = f"  (A와 겹침 {n}/{len(baseline)})"
    print(f"  {label}{overlap}")
    for title, score in results:
        mark = "" if baseline is None or title in baseline else "  ← A에 없음"
        print(f"     {score:6.3f}  {title}{mark}")


def main() -> int:
    http = httpx.Client(timeout=30)
    qdrant = QdrantClient(url=QDRANT_URL)

    print("=" * 70)
    print("1) Qwen3.6 서버 확인")
    try:
        r = http.get(f"{QWEN_BASE_URL}/models", timeout=10)
        r.raise_for_status()
        ids = [m.get("id") for m in r.json().get("data", [])]
        print(f"   OK  모델: {ids}")
        if QWEN_MODEL not in ids:
            print(f"   ⚠ 설정한 모델명 '{QWEN_MODEL}'이 목록에 없음 → QWEN_MODEL 확인 필요")
    except Exception as e:  # 점검 스크립트: 원인만 출력하고 중단
        print(f"   실패: {e}")
        return 1

    print("=" * 70)
    print("2) 검색 비교 (리랭커 상위 5)")
    timings: list[tuple[float, float]] = []
    for lang, foreign, korean in TEST_CASES:
        print("-" * 70)
        print(f"[{lang}] {foreign}")
        try:
            a = search(http, qdrant, korean)
            base = {t for t, _ in a}
            b = search(http, qdrant, foreign)

            t0 = time.perf_counter()
            translated = translate_to_korean(http, foreign)
            t1 = time.perf_counter()
            c = search(http, qdrant, translated)
            t2 = time.perf_counter()
            timings.append((t1 - t0, t2 - t1))
        except Exception as e:
            print(f"   실패: {type(e).__name__}: {e}")
            return 1

        print(f"  번역 결과: {translated}   (번역 {t1 - t0:.2f}s, 검색 {t2 - t1:.2f}s)")
        print_results(f"A. 한국어 기준: {korean}", a, None)
        print_results("B. 외국어 원문 검색", b, base)
        print_results("C. 번역 후 검색 (설계안)", c, base)

    print("=" * 70)
    if timings:
        avg_t = sum(t for t, _ in timings) / len(timings)
        avg_s = sum(s for _, s in timings) / len(timings)
        print(f"3) 평균 시간: 번역 {avg_t:.2f}s, 검색(임베딩+Qdrant+리랭커) {avg_s:.2f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
