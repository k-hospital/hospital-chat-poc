"""
chunks.json 재청킹 -> chunks_rechunked.json (서버 호출 없음)

기존 chunks.json은 길이 기준으로 잘려서 문단·표가 조각 경계에서 끊기고,
의료진 페이지가 전체의 절반을 차지하며(목록 조각엔 교수 최대 15명이 섞이고,
상세 조각엔 교수 이름이 없음) 검색 품질을 떨어뜨렸다. 이를 다시 나눈다.

처리 순서
  1. 페이지 복원: chunk_id의 '#' 앞부분이 같은 조각을 순서대로 이어 붙인다
     (조각마다 반복된 [제목] 줄과 반복된 소제목 줄은 뺀다)
  2. 페이지 제외
     - exclude_from_chatbot 조각
     - 직원용 페이지(수련교육부·IRB위원회)
     - 진료과 의료진 목록(doctor/list.do)·의사 상세 프로필(doctor/view.do)
       -> 의료진 정보는 적재 시 ish_doctors.json(1명 = 1조각)으로 대신한다
  3. 논문·연구 목록 블록 삭제 (어느 페이지든 "- 논문" 같은 목록 블록 통째로)
  4. 기존 정제 규칙(clean_text: 빈 표·반복 안내 문구 제거)을 페이지 단위로 적용
  5. 구조 기준 분할: 소제목(#) -> 문단 -> 줄 순서, 목표 TARGET_CHARS, 최대 MAX_CHARS
     - 표는 행 단위로 나누고 조각마다 표 머리글을 반복
     - 모든 조각 첫 줄은 "[페이지 제목]", 섹션 중간부터 시작하면 소제목 줄을 다시 넣음
  6. 센터 의료진 목록(centerDoctor/list.do)은 교수 1명 = 1조각으로 변환
     ("[건강증진센터 > 의료진] 건강증진센터 소속 가정의학과 황희진 교수 / 전문분야: ...")

사용법 (hospital_chatbot\data 폴더에서):
    python rechunk.py                 # chunks_rechunked.json 생성 + 통계
    python rechunk.py --show 5        # 샘플 조각 5개씩 출력 (일반·표·센터 의료진)

이후 적재:
    python insert_chunks_to_qdrant.py --src chunks_rechunked.json --collection hospital_chunks_test
"""

from __future__ import annotations

import argparse
import json
import random
import re
from collections import Counter, OrderedDict

from insert_chunks_to_qdrant import EXCLUDE_TITLE_KEYWORDS, clean_text

SRC_PATH = "chunks.json"
OUT_PATH = "chunks_rechunked.json"

TARGET_CHARS = 700   # 이 길이를 넘기면 다음 블록부터 새 조각
MAX_CHARS = 1000     # 블록 하나가 이보다 길면 줄/행 단위로 쪼갬
MIN_CHARS = 150      # 이보다 짧은 마지막 조각은 앞 조각에 붙임 (같은 섹션일 때만)

# 의료진 정보는 ish_doctors.json으로 대신하므로 제외할 페이지
DOCTOR_PAGE_URL_PARTS = ("/doctor/list.do", "/doctor/view.do")
CENTER_DOCTOR_URL_PART = "/centerDoctor/list.do"

# 이 이름으로 시작하는 목록 블록은 통째로 삭제 (의료진 논문·연구 이력 등)
DROP_LIST_HEADS = ("논문", "연구", "저서", "학술활동", "학회활동", "수상")
_DROP_HEAD_RE = re.compile(r"^-\s*(" + "|".join(DROP_LIST_HEADS) + r")\s*$")

_TITLE_LINE_RE = re.compile(r"^\[.*\]$")
_HEADING_RE = re.compile(r"^#{1,6}\s+\S")
_PROF_RE = re.compile(r"^(\S+)\s*교수$")


# ---------------------------------------------------------------------------
# 1. 페이지 복원
# ---------------------------------------------------------------------------

def _chunk_no(chunk_id: str) -> int:
    tail = chunk_id.rsplit("#", 1)[-1]
    return int(tail) if tail.isdigit() else 0


def rebuild_pages(raw: list[dict]) -> "OrderedDict[str, dict]":
    """chunk_id 앞부분별로 조각을 이어 붙여 페이지 원문을 복원한다."""
    groups: "OrderedDict[str, list[dict]]" = OrderedDict()
    for item in raw:
        if item.get("exclude_from_chatbot"):
            continue
        groups.setdefault(item["chunk_id"].rsplit("#", 1)[0], []).append(item)

    pages: "OrderedDict[str, dict]" = OrderedDict()
    for key, items in groups.items():
        items.sort(key=lambda x: _chunk_no(x["chunk_id"]))
        text = ""
        last_heading = None
        for item in items:
            lines = item.get("text", "").splitlines()
            if lines and _TITLE_LINE_RE.match(lines[0].strip()):
                lines = lines[1:]
            # 이전 조각에서 이어지는 소제목 반복 제거 (분할기가 조각마다 소제목을 다시 넣음)
            while lines and not lines[0].strip():
                lines = lines[1:]
            if lines and last_heading and lines[0].strip() == last_heading:
                lines = lines[1:]
            body = "\n".join(lines).strip()
            if not body:
                continue
            for ln in body.splitlines():
                if _HEADING_RE.match(ln.strip()):
                    last_heading = ln.strip()
            # 항상 줄바꿈으로 잇는다. 문장 끝 여부로 공백 연결을 시도했더니
            # '골다공증'처럼 문장부호 없이 끝나는 목록 줄이 다음 줄과 합쳐지는 문제가 있었음.
            text = body if not text else text + "\n" + body
        first = items[0]
        pages[key] = {
            "page_id": key,
            "title": first.get("title") or "",
            "category": first.get("category"),
            "source_url": first.get("source_url") or "",
            "crawled_at": first.get("crawled_at"),
            "doc_type": first.get("doc_type"),
            "text": text,
        }
    return pages


# ---------------------------------------------------------------------------
# 2~4. 제외 / 논문 블록 삭제 / 정제
# ---------------------------------------------------------------------------

def drop_list_blocks(text: str) -> tuple[str, int]:
    """'- 논문' 같은 목록 머리 줄과 그 아래 들여쓴 항목('- - ', '  - ')을 삭제."""
    out: list[str] = []
    dropped = 0
    skipping = False
    for line in text.splitlines():
        s = line.strip()
        if _DROP_HEAD_RE.match(s):
            skipping = True
            dropped += 1
            continue
        if skipping:
            # 하위 항목: '- - xxx' 또는 들여쓴 '  - xxx' 또는 들여쓴 이어지는 줄
            if s.startswith("- - ") or (line[:1].isspace() and s):
                continue
            if not s:
                continue
            skipping = False
        out.append(line)
    return "\n".join(out), dropped


# ---------------------------------------------------------------------------
# 5. 구조 기준 분할
# ---------------------------------------------------------------------------

def _blocks(text: str) -> list[tuple[str, str | None, list[str]]]:
    """본문 -> [(종류, 소제목, 줄들)]. 종류: 'heading' | 'table' | 'para'."""
    blocks: list[tuple[str, str | None, list[str]]] = []
    heading: str | None = None
    lines = text.splitlines()
    i = 0
    para: list[str] = []

    def flush_para():
        nonlocal para
        if any(l.strip() for l in para):
            blocks.append(("para", heading, para))
        para = []

    while i < len(lines):
        line = lines[i]
        s = line.strip()
        if _HEADING_RE.match(s):
            flush_para()
            heading = s
            blocks.append(("heading", heading, [s]))
            i += 1
        elif s.startswith("|"):
            flush_para()
            j = i
            while j < len(lines) and lines[j].strip().startswith("|"):
                j += 1
            blocks.append(("table", heading, lines[i:j]))
            i = j
        elif not s:
            flush_para()
            i += 1
        else:
            para.append(line)
            i += 1
    flush_para()
    return blocks


def _split_long(kind: str, lines: list[str]) -> list[list[str]]:
    """MAX_CHARS보다 긴 블록을 줄(표는 행) 단위로 쪼갠다. 표는 머리글을 반복."""
    header: list[str] = []
    body = lines
    if kind == "table" and len(lines) >= 2 and re.fullmatch(r"\s*\|(\s*:?-+:?\s*\|)+\s*", lines[1]):
        header, body = lines[:2], lines[2:]
    parts: list[list[str]] = []
    cur: list[str] = []
    size = sum(len(h) + 1 for h in header)
    for ln in body:
        if cur and size + len(ln) + 1 > TARGET_CHARS:
            parts.append(header + cur)
            cur, size = [], sum(len(h) + 1 for h in header)
        cur.append(ln)
        size += len(ln) + 1
    if cur:
        parts.append(header + cur)
    return parts


def split_page(page: dict) -> list[str]:
    """페이지 본문 -> 조각 본문 목록 (각 조각 첫 줄 [제목] 포함)."""
    prefix = f"[{page['title']}]"
    pieces: list[tuple[str | None, str]] = []  # (소제목, 내용)

    cur: list[str] = []
    cur_heading: str | None = None
    size = 0

    def emit():
        nonlocal cur, size
        if any(l.strip() for l in cur):
            pieces.append((cur_heading, "\n".join(cur).strip()))
        cur, size = [], 0

    for kind, heading, lines in _blocks(page["text"]):
        if kind == "heading":
            emit()
            cur_heading = heading
            cur, size = [lines[0]], len(lines[0])
            continue
        block_len = sum(len(l) + 1 for l in lines)
        sub_blocks = _split_long(kind, lines) if block_len > MAX_CHARS else [lines]
        for sb in sub_blocks:
            sb_len = sum(len(l) + 1 for l in sb)
            if cur and size + sb_len > TARGET_CHARS and size > len(cur_heading or ""):
                emit()
            if not cur and cur_heading:
                # 섹션 중간부터 시작하는 조각엔 소제목을 다시 넣어 맥락 유지
                cur, size = [cur_heading], len(cur_heading)
            cur.extend(sb + [""])
            size += sb_len + 1
    emit()

    # 내용 없이 소제목만 남은 조각 제거, 너무 짧은 조각은 같은 섹션의 앞 조각에 붙임
    merged: list[tuple[str | None, str]] = []
    for heading, content in pieces:
        if heading and content.strip() == heading:
            continue
        if merged and len(content) < MIN_CHARS and merged[-1][0] == heading \
                and len(merged[-1][1]) + len(content) <= MAX_CHARS:
            body = content
            if heading and body.startswith(heading):
                body = body[len(heading):].strip()
            merged[-1] = (heading, merged[-1][1] + "\n\n" + body)
        else:
            merged.append((heading, content))
    return [f"{prefix}\n{content}" for _, content in merged]


# ---------------------------------------------------------------------------
# 6. 센터 의료진 목록 -> 1명 1조각
# ---------------------------------------------------------------------------

def center_doctor_chunks(page: dict) -> list[dict]:
    """'진료과 / OOO 교수 / 빠른진료 : / 전문분야' 반복 구조를 교수별 조각으로."""
    center = page["title"].split(">")[-1].strip().replace(" 소개", "")  # '건강증진센터'
    lines = [l.strip() for l in page["text"].splitlines()]
    lines = [l for l in lines if l and not l.startswith("빠른진료") and not l.startswith("|")
             and not _HEADING_RE.match(l)]
    idx = [i for i, l in enumerate(lines) if _PROF_RE.match(l)]
    docs: list[dict] = []
    for n, i in enumerate(idx):
        name = lines[i]
        dept = lines[i - 1] if i > 0 else center
        end = (idx[n + 1] - 1) if n + 1 < len(idx) else len(lines)
        # 전문분야가 비어 있으면 센터명·'교수' 같은 꼬리표 줄만 남으므로 걸러낸다
        spec = ", ".join(l for l in lines[i + 1:end] if l not in (center, "교수"))
        who = f"{center} 소속 {dept} {name}" if dept != center else f"{center} {name}"
        text = f"[{center} > 의료진]\n{who}"
        if spec:
            text += f"\n전문분야: {spec}"
        docs.append({
            "chunk_id": f"{page['page_id']}#doctor{n:03d}",
            "title": f"{center} > 의료진",
            "category": page["category"],
            "source_url": page["source_url"],
            "crawled_at": page["crawled_at"],
            "doc_type": page["doc_type"],
            "exclude_from_chatbot": False,
            "char_count": len(text),
            "text": text,
            "_key": (center, dept, name),
        })
    return docs


# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--show", type=int, default=0, help="종류별 샘플 조각 출력 개수")
    args = ap.parse_args()

    with open(SRC_PATH, encoding="utf-8") as f:
        raw = json.load(f)

    stats: Counter = Counter()
    stats["원본_조각"] = len(raw)
    stats["원본_제외표시_조각"] = sum(1 for r in raw if r.get("exclude_from_chatbot"))

    pages = rebuild_pages(raw)
    stats["복원_페이지"] = len(pages)

    out: list[dict] = []
    seen_center_doctors: set[tuple] = set()
    for page in pages.values():
        title, url = page["title"], page["source_url"]
        if any(k in title for k in EXCLUDE_TITLE_KEYWORDS):
            stats["제외_직원용페이지"] += 1
            continue
        if any(p in url for p in DOCTOR_PAGE_URL_PARTS):
            stats["제외_의료진목록·상세(ish_doctors로 대체)"] += 1
            continue

        text, n_drop = drop_list_blocks(page["text"])
        stats["삭제_논문·연구_목록블록"] += n_drop
        page["text"] = clean_text(text)

        if CENTER_DOCTOR_URL_PART in url:
            for d in center_doctor_chunks(page):
                key = d.pop("_key")
                if key in seen_center_doctors:   # h1/h2 두 페이지에 같은 교수 중복
                    stats["센터의료진_중복"] += 1
                    continue
                seen_center_doctors.add(key)
                out.append(d)
                stats["생성_센터의료진_조각"] += 1
            continue

        for n, text in enumerate(split_page(page)):
            out.append({
                "chunk_id": f"{page['page_id']}#r{n:03d}",
                "title": title,
                "category": page["category"],
                "source_url": url,
                "crawled_at": page["crawled_at"],
                "doc_type": page["doc_type"],
                "exclude_from_chatbot": False,
                "char_count": len(text),
                "text": text,
            })
            stats["생성_일반조각"] += 1

    stats["결과_조각_합계"] = len(out)
    lens = sorted(d["char_count"] for d in out)
    remaining_papers = sum(1 for d in out if "논문" in d["text"])

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)

    print("재청킹 결과:")
    for k, v in stats.items():
        print(f"  {k}: {v}")
    if lens:
        print(f"  조각 길이 최소/중앙/평균/최대: {lens[0]} / {lens[len(lens) // 2]} / "
              f"{sum(lens) // len(lens)} / {lens[-1]}")
        over = sum(1 for x in lens if x > MAX_CHARS + 100)
        print(f"  {MAX_CHARS + 100}자 초과 조각: {over}")
    print(f"  '논문' 단어가 남은 조각: {remaining_papers} (안내 문구 등 확인용)")
    print(f"저장: {OUT_PATH}")

    if args.show:
        rnd = random.Random(0)
        groups = {
            "일반 안내": [d for d in out if "#r" in d["chunk_id"] and "|" not in d["text"]],
            "표 포함": [d for d in out if "#r" in d["chunk_id"] and "|" in d["text"]],
            "센터 의료진": [d for d in out if "#doctor" in d["chunk_id"]],
        }
        for name, items in groups.items():
            print("=" * 70)
            print(f"[샘플] {name} ({len(items)}개 중 {min(args.show, len(items))}개)")
            for d in rnd.sample(items, min(args.show, len(items))):
                print("-" * 70)
                print(f"{d['chunk_id']}  ({d['char_count']}자)")
                print(d["text"][:600] + (" …" if len(d["text"]) > 600 else ""))


if __name__ == "__main__":
    main()
