"""
조합 데이터 만들기 -> chunks_combined.json (서버 호출 없음)

  홈페이지 크롤링/rag_chunks.jsonl  (섹션 단위 + context, 113페이지)   ← 기본
+ chunks_rechunked.json 중 rag_chunks에 없는 URL의 조각                  ← 범위 보완
                                    (건강검진 세부, 검사실, 오시는 길, 센터 의료진 등)
  (의료진 ish_doctors.json은 적재 스크립트가 붙임)

출력 형식은 chunks.json과 같아서 그대로 적재할 수 있다:
    python rechunk.py              # chunks_rechunked.json 먼저 생성
    python combine_chunks.py
    python insert_chunks_to_qdrant.py --src chunks_combined.json --collection hospital_chunks_test
"""

from __future__ import annotations

import json
import re
from collections import Counter

from insert_chunks_to_qdrant import EXCLUDE_TITLE_KEYWORDS

RAG_PATH = "홈페이지 크롤링/rag_chunks.jsonl"
RECHUNKED_PATH = "chunks_rechunked.json"
OUT_PATH = "chunks_combined.json"

# 진료과·센터 페이지 본문 앞에 남은 메뉴 글자
NAV_WORDS = {"진료과 전체보기", "진료과 위치", "센터 전체보기", "센터 위치"}
_SHORT_MENU_RE = re.compile(r"^-\s*\S.{0,13}$")  # "- 소개", "- 의료진" 같은 짧은 메뉴 줄


def strip_leading_nav(text: str) -> str:
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        s = lines[i].strip()
        if not s or s in NAV_WORDS or _SHORT_MENU_RE.match(s):
            i += 1
            continue
        break
    return "\n".join(lines[i:]).strip()


def main() -> None:
    rag = [json.loads(line) for line in open(RAG_PATH, encoding="utf-8") if line.strip()]
    with open(RECHUNKED_PATH, encoding="utf-8") as f:
        rechunked = json.load(f)

    stats: Counter = Counter()
    out: list[dict] = []
    rag_urls: set[str] = set()

    id_count: Counter = Counter()
    for r in rag:
        rag_urls.add(r["url"])
        # 2026-10-06: 페이지 제목·섹션·경로가 모두 빈 조각은 본문 없이 사이트 메뉴 글자만 있는 잡음
        # (health_intro.do 5조각: "대메뉴로 바로가기 / 병원소개 / … / IRB위원회 / 수련교육부") → 제외
        if not (r.get("page_title") or "").strip() and not (r.get("section") or "").strip() \
                and not (r.get("breadcrumb") or "").strip():
            stats["rag_제목없는메뉴조각제외"] += 1
            continue
        title = r["page_title"] + (f" > {r['section']}" if r.get("section") else "")
        if any(k in title for k in EXCLUDE_TITLE_KEYWORDS):
            stats["rag_직원용제외"] += 1
            continue
        body = strip_leading_nav(r["text"])
        if body != r["text"].strip():
            stats["rag_메뉴글자제거"] += 1
        if len(body) < 30:
            stats["rag_내용부족제외"] += 1
            continue
        text = f"[{r['context']}]\n{body}"
        # rag_chunks.jsonl의 id는 같은 페이지 조각끼리 중복됨(239건) → 페이지 안 순번을 붙여 고유하게
        n = id_count[r["id"]]
        id_count[r["id"]] += 1
        out.append({
            "chunk_id": f"{r['id']}#{n:02d}",
            "title": title,
            "category": r["category"],
            "source_url": r["url"],
            "crawled_at": None,
            "doc_type": "환자용",
            "exclude_from_chatbot": False,
            "char_count": len(text),
            "text": text,
        })
        stats["rag_사용"] += 1

    for c in rechunked:
        if c["source_url"] in rag_urls:
            stats["재청킹_중복URL제외"] += 1
            continue
        out.append(c)
        stats["재청킹_보완"] += 1

    stats["합계"] = len(out)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print("조합 결과:")
    for k, v in stats.items():
        print(f"  {k}: {v}")
    print("보완 조각 분류:", dict(Counter(c["category"] for c in out if not c["chunk_id"].startswith("ish_"))))
    ids = [c["chunk_id"] for c in out]
    print(f"chunk_id 중복: {len(ids) - len(set(ids))}건, 제목 빈 조각: {sum(1 for c in out if not (c['title'] or '').strip())}건")
    print(f"저장: {OUT_PATH}")


if __name__ == "__main__":
    main()
