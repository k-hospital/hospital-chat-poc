"""
chunks.json -> 노이즈 정제 -> dense/sparse 임베딩 -> Qdrant 'hospital_chunks' 컬렉션 적재

사용법 (hospital_chatbot\data 폴더에서):
    python insert_chunks_to_qdrant.py --dry-run   # 정제 결과만 확인. 서버 호출 없음, chunks_cleaned.json 생성
    python insert_chunks_to_qdrant.py             # 실제 적재 (hospital_chunks 컬렉션을 새로 만듦)

    # 실험용: 운영 컬렉션은 그대로 두고 다른 컬렉션에 적재
    python insert_chunks_to_qdrant.py --collection hospital_chunks_test --exclude-doctor-profiles

    # sparse 서버가 바뀐 경우 (예: bge-m3 sparse 서버 sparse_embed_server)
    # --cache: sparse 계산 결과를 파일에 저장해서, 취소했다가 다시 실행해도 이어서 진행
    python insert_chunks_to_qdrant.py --src chunks_combined.json --cache sparse_cache.jsonl
    # (sparse 기본 주소 .32:8083 = sparse_gpu_wrapper. 다른 서버를 쓸 때만 --sparse-url 지정)

    # 재청킹 결과(rechunk.py가 만든 chunks_rechunked.json)로 적재
    python insert_chunks_to_qdrant.py --src chunks_rechunked.json --collection hospital_chunks_test

정제 규칙:
  1. exclude_from_chatbot=true 인 조각 제외 (약관·정책, 홍보·소식)
     + 환자용이 아닌 직원용 페이지 제외: 수련교육부(전공의 교육과정 등), IRB위원회
       (크롤링 때 '병원이용안내(일반)'으로 분류돼 있지만 환자 안내와 무관하고,
        교육용 의학 내용이 증상 질문 검색을 오염시킴)
  2. 내용이 전부 빈 표(진료시간표·달력 등) 제거 — 사이트가 자바스크립트로 그려서 빈 표만 수집됨
     (비급여진료비처럼 값이 들어있는 표는 그대로 유지)
  3. "모바일로 확인하실 경우..." 같은 반복 안내 문구 제거
  4. 정제 후 본문이 너무 짧은 조각 제외
  5. 정제 후 내용이 완전히 같은 조각은 하나만 남김

의료진 보충 (ish_doctors.json):
  chunks.json 크롤링에서 소아청소년과 의료진 페이지가 빠졌고, 일부 교수는 전문분야 문장이
  다른 교수와 같아서 중복 제거로 지워졌습니다. 이를 메우려고 의료진 171명 목록을
  "진료과 + 교수 + 전문분야" 조각으로 만들어 함께 적재합니다. (끄려면 --no-doctors)

의사 상세 프로필 제외 (--exclude-doctor-profiles, 기본은 꺼짐):
  의사 상세 페이지(doctor/view.do)는 크롤링 때 교수 이름·진료과 머리글이 빠져서
  경력·논문 조각만 남았고, 제목도 전부 '의료진 > 진료과ㆍ의료진 > 진료ㆍ예약'으로 같습니다.
  누구의 내용인지 알 수 없어 의료진 추천에 쓸 수 없고, 논문 속 질병 단어 때문에
  증상 검색 후보를 차지합니다. 의료진 추천은 ish_doctors.json 보충 조각으로 대신합니다.

기존 'hospital_doctors' 컬렉션은 건드리지 않습니다 (필요하면 되돌리기용).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time

COLLECTION_NAME = "hospital_chunks"
try:  # 사내 서버 주소·모델 이름은 ai-backend/.env 에서 읽는다 (저장소에 적지 않음)
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "ai-backend", ".env"))
except ImportError:
    pass

QDRANT_URL = os.environ.get("QDRANT_URL", "")
DENSE_EMBEDDING_URL = os.environ.get("DENSE_EMBEDDING_URL", "")
DENSE_MODEL = "BAAI/bge-m3"
SPARSE_EMBEDDING_URL = os.environ.get("SPARSE_EMBEDDING_URL", "")
VECTOR_SIZE = 1024
BATCH_SIZE = 16          # 임베딩/업로드를 몇 건씩 묶어서 보낼지
MIN_BODY_CHARS = 30      # 정제 후 본문이 이보다 짧으면 제외

SRC_PATH = "chunks.json"
DOCTORS_PATH = "ish_doctors.json"
_HOME = "https://www.ish.or.kr/main"
# 진료과별 의료진 목록 페이지 (출처 카드 링크용)
DEPT_URL = {
    "가정의학과": 4, "감염내과": 5, "내분비대사내과": 49, "류마티스내과": 50, "마취통증의학과": 51,
    "방사선종양학과": 52, "병리과": 53, "비뇨의학과": 54, "산부인과": 55, "성형외과": 56,
    "소화기내과": 58, "신경과": 59, "신경외과": 60, "신장내과": 61, "심장내과": 62,
    "심장혈관흉부외과": 79, "안과": 63, "알레르기면역내과": 80, "영상의학과": 64, "외과": 65,
    "응급의학과": 66, "이비인후-두경부외과": 67, "재활의학과": 68, "정신건강의학과": 69, "정형외과": 70,
    "종양혈액내과": 71, "중환자내과": 93, "직업환경의학과": 72, "진단검사의학과": 73, "치과": 74,
    "피부과": 75, "한의과": 78, "핵의학과": 76, "호흡기내과": 77,
}
CLEANED_PATH = "chunks_cleaned.json"

BOILERPLATE = {
    "모바일로 확인하실 경우 표를 좌우로 움직여 내용을 확인 하실 수 있습니다.",
    "진료시간표는 사정에 따라 변경될 수 있습니다.",
    "진료일자 및 시간은 사정에 따라 변경될 수 있습니다.",
    "선택하신 의료진은 전화예약 또는 첫 진료 고객 상담으로 예약을 진행하고 있습니다.",
    "시작",
    "멈춤",
}
# 제목(title)에 이 단어가 들어간 페이지는 직원용이라 제외
EXCLUDE_TITLE_KEYWORDS = ("수련교육부", "IRB위원회")
# 의사 상세 프로필 페이지 (--exclude-doctor-profiles 일 때 제외)
DOCTOR_PROFILE_URL_PART = "/doctor/view.do"

_SEPARATOR_RE = re.compile(r"\s*\|(\s*:?-+:?\s*\|)+\s*")
_EMPTY_LABEL_RE = re.compile(r"빠른진료\s*:?")


# ---------------------------------------------------------------------------
# 1. 정제
# ---------------------------------------------------------------------------

def _is_table_line(line: str) -> bool:
    return line.lstrip().startswith("|")


def _cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _table_is_empty(block: list[str]) -> bool:
    """구분선(|---|) 아래 데이터 행이 없거나, 모든 행의 첫 칸 이후가 전부 비어 있으면 빈 표."""
    sep_idx = next((i for i, l in enumerate(block) if _SEPARATOR_RE.fullmatch(l)), None)
    if sep_idx is None:
        return False  # 구분선 없는 표는 판단하지 않고 유지
    data_rows = block[sep_idx + 1:]
    if not data_rows:
        return True
    def row_empty(row: str) -> bool:
        cells = _cells(row)
        # 여러 칸짜리 행: 첫 칸(오전/오후 같은 라벨)을 뺀 나머지가 전부 비어야 빈 행
        # 한 칸짜리 행(FAQ 등): 그 칸이 비어야 빈 행
        return not any(cells[1:]) if len(cells) > 1 else not cells[0]

    return all(row_empty(r) for r in data_rows)


def clean_text(text: str) -> str:
    lines = text.splitlines()
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if _is_table_line(line):
            j = i
            while j < len(lines) and _is_table_line(lines[j]):
                j += 1
            block = lines[i:j]
            if _table_is_empty(block):
                # 빈 진료시간표 바로 위의 "### OOO 교수 진료시간표" 제목도 함께 제거
                k = len(out) - 1
                while k >= 0 and not out[k].strip():
                    k -= 1
                if k >= 0 and out[k].lstrip().startswith("#") and "진료시간표" in out[k]:
                    del out[k:]
            else:
                out.extend(block)
            i = j
            continue
        s = line.strip()
        if s in BOILERPLATE or _EMPTY_LABEL_RE.fullmatch(s):
            i += 1
            continue
        out.append(line)
        i += 1

    # 연속 빈 줄 / 연속으로 똑같이 반복되는 줄 정리
    result: list[str] = []
    for line in out:
        if not line.strip():
            if result and result[-1].strip():
                result.append("")
            continue
        if result and line.strip() == result[-1].strip():
            continue
        # 빈 줄 하나 건너 똑같은 줄이 반복되는 경우 (A, "", A)
        if len(result) >= 2 and not result[-1].strip() and line.strip() == result[-2].strip():
            continue
        result.append(line)
    return "\n".join(result).strip()


def _body(text: str) -> str:
    """첫 줄이 [제목] 형태면 그 줄을 뺀 본문."""
    lines = text.splitlines()
    if lines and lines[0].startswith("[") and lines[0].rstrip().endswith("]"):
        lines = lines[1:]
    return "\n".join(lines).strip()


def load_and_clean(path: str, exclude_doctor_profiles: bool = False) -> tuple[list[dict], dict]:
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)

    stats = {"원본": len(raw), "제외표시(exclude_from_chatbot)": 0, "직원용페이지(수련교육부·IRB)": 0,
             "정제후_내용부족": 0, "중복": 0}
    if exclude_doctor_profiles:
        stats["의사상세프로필"] = 0
    seen: set[str] = set()
    cleaned: list[dict] = []
    for item in raw:
        if item.get("exclude_from_chatbot"):
            stats["제외표시(exclude_from_chatbot)"] += 1
            continue
        if any(k in (item.get("title") or "") for k in EXCLUDE_TITLE_KEYWORDS):
            stats["직원용페이지(수련교육부·IRB)"] += 1
            continue
        if exclude_doctor_profiles and DOCTOR_PROFILE_URL_PART in (item.get("source_url") or ""):
            stats["의사상세프로필"] += 1
            continue
        text = clean_text(item.get("text", ""))
        if len(_body(text)) < MIN_BODY_CHARS:
            stats["정제후_내용부족"] += 1
            continue
        if text in seen:
            stats["중복"] += 1
            continue
        seen.add(text)
        cleaned.append({
            "chunk_id": item.get("chunk_id"),
            "title": item.get("title"),
            "category": item.get("category"),
            "source_url": item.get("source_url"),
            "crawled_at": item.get("crawled_at"),
            "text": text,
        })
    stats["적재대상"] = len(cleaned)
    return cleaned, stats


def load_lay_terms(path: str | None) -> dict:
    """doctor_lay_terms.json(make_lay_terms.py 생성, 사람 검수) → {(진료과, 교수): [쉬운 말]}. 검수된 항목만."""
    if not path:
        return {}
    with open(path, encoding="utf-8") as f:
        rows = json.load(f)
    return {(r["dept"], r["doctor"]): r["lay_terms"] for r in rows if r.get("reviewed") and r.get("lay_terms")}


def load_doctors(path: str, lay_terms: dict | None = None) -> list[dict]:
    """ish_doctors.json(dept/doctor/specialty) -> 의료진 1명당 조각 1개.
    lay_terms가 있으면 '관련 증상·부위: …' 줄을 붙인다 (환자 표현 ↔ 전문분야 용어 차이 보완)."""
    with open(path, encoding="utf-8") as f:
        rows = json.load(f)
    lay_terms = lay_terms or {}
    docs = []
    for r in rows:
        dept, doctor, specialty = r.get("dept", ""), r.get("doctor", ""), r.get("specialty", "")
        if not dept or not doctor or "일반의" in doctor:  # 'OS일반의' 같은 가상 항목 제외
            continue
        if dept == "소아청소년과":
            url = f"{_HOME}/center_doctor/list.do?center_idx=52"
        elif dept in DEPT_URL:
            url = f"{_HOME}/doctor/list.do?part_idx={DEPT_URL[dept]}"
        else:
            url = f"{_HOME}/part/list.do"
        docs.append({
            "chunk_id": f"의료진목록/{dept}/{doctor}",
            "title": f"{dept} > 의료진",
            "category": "의료진",
            "source_url": url,
            "crawled_at": "2026-09-10",
            "text": f"[{dept} > 의료진]\n{dept} {doctor}\n전문분야: {specialty}"
                    + (f"\n관련 증상·부위: {', '.join(lay_terms[(dept, doctor)])}" if (dept, doctor) in lay_terms else ""),
        })
    return docs


# ---------------------------------------------------------------------------
# 2. 임베딩 (배치)
# ---------------------------------------------------------------------------

def embed_dense(session, texts: list[str]) -> list[list[float]]:
    resp = session.post(DENSE_EMBEDDING_URL, json={"model": DENSE_MODEL, "input": texts}, timeout=120)
    resp.raise_for_status()
    data = sorted(resp.json()["data"], key=lambda d: d["index"])
    return [d["embedding"] for d in data]


def embed_sparse(session, texts: list[str]) -> list[tuple[list[int], list[float]]]:
    resp = session.post(SPARSE_EMBEDDING_URL, json={"inputs": texts, "truncate": True}, timeout=120)
    resp.raise_for_status()
    out = []
    for item in resp.json():
        if isinstance(item, dict) and "indices" in item:
            out.append((list(item["indices"]), [float(v) for v in item["values"]]))
        else:
            out.append(([int(x["index"]) for x in item], [float(x["value"]) for x in item]))
    return out


# ---------------------------------------------------------------------------
# 3. 적재
# ---------------------------------------------------------------------------

def load_sparse_cache(path: str | None) -> dict:
    """--cache 파일(JSON Lines)에서 이미 계산한 sparse 값을 읽는다."""
    cache: dict = {}
    if not path:
        return cache
    import os
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:   # 중간에 끊겨 마지막 줄이 깨진 경우
                    continue
                cache[row["k"]] = (row["i"], row["v"])
    return cache


def embed_sparse_cached(session, texts: list[str], cache: dict, cache_file) -> list[tuple[list[int], list[float]]]:
    """캐시에 없는 문장만 sparse 서버에 보내고, 계산 결과는 즉시 파일에 이어 쓴다.
    캐시 키에 서버 주소를 포함해서, sparse 서버(모델)가 바뀌면 이전 값을 재사용하지 않는다."""
    keys = [hashlib.sha1((SPARSE_EMBEDDING_URL + "\n" + t).encode("utf-8")).hexdigest() for t in texts]
    missing = [i for i, k in enumerate(keys) if k not in cache]
    if missing:
        got = embed_sparse(session, [texts[i] for i in missing])
        for i, g in zip(missing, got):
            cache[keys[i]] = g
            if cache_file:
                cache_file.write(json.dumps({"k": keys[i], "i": g[0], "v": g[1]}) + "\n")
        if cache_file:
            cache_file.flush()
    return [cache[k] for k in keys]


def upload(docs: list[dict], collection: str = COLLECTION_NAME, cache_path: str | None = None) -> None:
    import requests
    from qdrant_client import QdrantClient
    from qdrant_client.http import models

    client = QdrantClient(url=QDRANT_URL, timeout=120)
    if client.collection_exists(collection):
        client.delete_collection(collection)
    client.create_collection(
        collection_name=collection,
        vectors_config={"text-dense": models.VectorParams(size=VECTOR_SIZE, distance=models.Distance.COSINE)},
        sparse_vectors_config={"text-sparse": models.SparseVectorParams()},
    )
    print(f"컬렉션 '{collection}' 생성 완료")

    session = requests.Session()
    sparse_cache = load_sparse_cache(cache_path)
    cache_file = open(cache_path, "a", encoding="utf-8") if cache_path else None
    if cache_path:
        print(f"sparse 캐시: {cache_path} (이미 계산된 {len(sparse_cache)}건 재사용)")
    started = time.time()
    total = len(docs)
    for start in range(0, total, BATCH_SIZE):
        batch = docs[start:start + BATCH_SIZE]
        texts = [d["text"] for d in batch]
        try:
            dense = embed_dense(session, texts)
            sparse = embed_sparse_cached(session, texts, sparse_cache, cache_file)
            points = [
                models.PointStruct(
                    id=start + i + 1,
                    vector={
                        "text-dense": dense[i],
                        "text-sparse": models.SparseVector(indices=sparse[i][0], values=sparse[i][1]),
                    },
                    payload=doc,
                )
                for i, doc in enumerate(batch)
            ]
            client.upsert(collection_name=collection, points=points, wait=True)
        except Exception as e:
            # 자동 재시도하지 않고 어디서 멈췄는지 알려준 뒤 종료
            print(f"\n[실패] {start + 1}~{start + len(batch)}번째 배치에서 오류: {e}", file=sys.stderr)
            print(f"첫 문서 chunk_id: {batch[0]['chunk_id']}", file=sys.stderr)
            sys.exit(1)
        done = start + len(batch)
        print(f"\r{done}/{total} 적재 ({time.time() - started:.0f}초)", end="", flush=True)

    if cache_file:
        cache_file.close()
    count = client.count(collection, exact=True).count
    print(f"\n완료: Qdrant '{collection}' 컬렉션에 {count}건 적재됨")


def main() -> None:
    global SPARSE_EMBEDDING_URL
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="정제 결과만 확인 (서버 호출 없음)")
    parser.add_argument("--no-doctors", action="store_true", help="ish_doctors.json 의료진 보충을 하지 않음")
    parser.add_argument("--exclude-doctor-profiles", action="store_true",
                        help="이름 없는 의사 상세 프로필 조각(doctor/view.do) 제외")
    parser.add_argument("--src", default=SRC_PATH,
                        help=f"입력 조각 파일 (기본 {SRC_PATH}, 재청킹 결과는 chunks_rechunked.json)")
    parser.add_argument("--collection", default=COLLECTION_NAME,
                        help=f"적재할 컬렉션 이름 (기본 {COLLECTION_NAME}, 실험 시 다른 이름 사용)")
    parser.add_argument("--lay-terms", default=None,
                        help="의료진 쉬운 말 파일 (doctor_lay_terms.json, 검수된 항목만 사용). 의료진 조각에 '관련 증상·부위' 줄 추가")
    parser.add_argument("--cache", default=None,
                        help="sparse 계산 결과를 저장·재사용할 파일 (예: sparse_cache.jsonl). 취소 후 이어하기, 컬렉션 재적재 시 재계산 방지")
    parser.add_argument("--sparse-url", default=SPARSE_EMBEDDING_URL,
                        help=f"sparse 임베딩 서버 주소 (기본 {SPARSE_EMBEDDING_URL})")
    args = parser.parse_args()
    SPARSE_EMBEDDING_URL = args.sparse_url

    docs, stats = load_and_clean(args.src, exclude_doctor_profiles=args.exclude_doctor_profiles)
    if not args.no_doctors:
        import os
        if os.path.exists(DOCTORS_PATH):
            lay = load_lay_terms(args.lay_terms)
            doctors = load_doctors(DOCTORS_PATH, lay)
            if args.lay_terms:
                stats["의료진_쉬운말적용"] = sum(1 for d in doctors if "관련 증상·부위" in d["text"])
            docs.extend(doctors)
            stats["보충_의료진"] = len(doctors)
            stats["적재대상"] = len(docs)
        else:
            print(f"[안내] {DOCTORS_PATH} 가 없어 의료진 보충 없이 진행합니다.")
    print("정제 결과:", json.dumps(stats, ensure_ascii=False))
    # 실험용 컬렉션이면 운영 기준 확인 파일(chunks_cleaned.json)을 덮어쓰지 않도록 이름을 나눈다
    cleaned_path = (CLEANED_PATH if args.collection == COLLECTION_NAME
                    else CLEANED_PATH.replace(".json", f"_{args.collection}.json"))
    with open(cleaned_path, "w", encoding="utf-8") as f:
        json.dump(docs, f, ensure_ascii=False, indent=1)
    print(f"정제된 데이터를 {cleaned_path} 에 저장했습니다 (확인용).")

    if args.dry_run:
        return
    upload(docs, args.collection, args.cache)


if __name__ == "__main__":
    main()
