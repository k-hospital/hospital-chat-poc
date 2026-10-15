"""
의료진 '쉬운 말' 초안 생성 — 환자 표현(손목·속쓰림)과 데이터 용어(수부외과·소화기내과)의 차이를 메우기 위해
각 의료진 조각에 붙일 "관련 증상·부위" 목록을 Qwen3.6으로 만든다. **사람 검수 후에만 적재에 쓴다.**

입력 : ish_doctors.json (진료과·교수·전문분야)
출력 : doctor_lay_terms.json      적재용 (교수별 lay_terms, reviewed=false로 시작)
       doctor_lay_terms_검수.csv  엑셀 검수용 (진료과별 정렬, '수정안'·'확인' 칸에 기입)

같은 (진료과, 전문분야)는 한 번만 호출한다. 기존 doctor_lay_terms.json이 있으면 덮어쓰지 않고 중단
(검수 내용이 지워지지 않게). 다시 만들려면 --force.

실행: python make_lay_terms.py [--force]
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys

import httpx

try:  # 사내 서버 주소·모델 이름은 ai-backend/.env 에서 읽는다 (저장소에 적지 않음)
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "ai-backend", ".env"))
except ImportError:
    pass

LLM_URL = os.environ.get("LLM_BASE_URL", "").rstrip("/") + "/chat/completions"
LLM_MODEL = os.environ.get("LLM_MODEL", "")
SRC = "ish_doctors.json"
OUT_JSON = "doctor_lay_terms.json"
OUT_CSV = "doctor_lay_terms_검수.csv"

PROMPT = """\
당신은 한국 병원 안내 데이터를 만드는 사람입니다.
아래 의료진의 진료과와 전문분야를 보고, 환자가 이 의사를 찾을 때 실제로 말할 법한 **쉬운 표현**을 만드세요.

규칙:
- 신체 부위와 증상 위주의 일상어 5~10개 (예: 수부외과 → 손목 통증, 손 저림, 손가락 통증, 손목 골절)
- 전문분야에 해당하는 부위·증상만. 다른 부위나 다른 진료과 영역은 넣지 말 것
- 병명·진단명·치료법보다 환자가 느끼는 증상 표현을 우선
- 영상의학과·병리과·진단검사의학과·핵의학과처럼 환자가 증상으로 직접 찾지 않는 경우는 "없음"
- 출력은 쉼표로 구분한 목록 한 줄만 (설명·번호·따옴표 없이)"""


MAX_TERMS = 12


def clean_terms(terms: list[str]) -> list[str]:
    """중복 제거(순서 유지) + 최대 MAX_TERMS개. 모델이 같은 말을 반복 생성하는 경우 대비 (김상희 교수 사례)."""
    return list(dict.fromkeys(t for t in terms if t))[:MAX_TERMS]


def write_csv(rows: list[dict]) -> None:
    with open(OUT_CSV, "w", encoding="utf-8-sig", newline="") as f:   # utf-8-sig: 엑셀에서 한글 깨짐 방지
        w = csv.writer(f)
        w.writerow(["진료과", "교수", "전문분야", "쉬운 말(초안)", "수정안(고칠 때만)", "확인(O/X)"])
        for r in sorted(rows, key=lambda x: (x["dept"], x["doctor"])):
            w.writerow([r["dept"], r["doctor"], r["specialty"], ", ".join(r["lay_terms"]), "", ""])


def ask(client: httpx.Client, dept: str, specialty: str) -> str:
    r = client.post(LLM_URL, json={
        "model": LLM_MODEL,
        "messages": [{"role": "system", "content": PROMPT},
                     {"role": "user", "content": f"진료과: {dept}\n전문분야: {specialty or '(기재 없음)'}"}],
        "temperature": 0, "max_tokens": 200,
        "chat_template_kwargs": {"enable_thinking": False},
    }, timeout=60)
    r.raise_for_status()
    msg = r.json()["choices"][0]["message"]
    return (msg.get("content") or msg.get("reasoning_content") or "").strip().splitlines()[0].strip()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="기존 doctor_lay_terms.json을 덮어씀 (검수 내용 사라짐)")
    ap.add_argument("--clean-only", action="store_true",
                    help="LLM 호출 없이 기존 JSON의 중복만 정리하고 검수 CSV를 다시 만듦 (검수 전 단계에서만)")
    args = ap.parse_args()
    if args.clean_only:
        with open(OUT_JSON, encoding="utf-8") as f:
            rows = json.load(f)
        if any(r.get("reviewed") for r in rows):
            print("검수된 항목이 있어 CSV를 다시 만들지 않습니다 (검수 내용 보호).")
            return 1
        changed = 0
        for r in rows:
            c = clean_terms(r["lay_terms"])
            changed += c != r["lay_terms"]
            r["lay_terms"] = c
        with open(OUT_JSON, "w", encoding="utf-8") as f:
            json.dump(rows, f, ensure_ascii=False, indent=1)
        write_csv(rows)
        print(f"정리 완료: {changed}명 수정, 저장 {OUT_JSON}, {OUT_CSV}")
        return 0
    if os.path.exists(OUT_JSON) and not args.force:
        print(f"{OUT_JSON}이 이미 있어 중단합니다 (검수 내용 보호). 다시 만들려면 --force")
        return 1

    with open(SRC, encoding="utf-8") as f:
        doctors = [d for d in json.load(f) if d.get("dept") and d.get("doctor") and "일반의" not in d["doctor"]]

    client = httpx.Client()
    cache: dict[tuple, list[str]] = {}
    rows = []
    for i, d in enumerate(doctors, start=1):
        key = (d["dept"], d.get("specialty", ""))
        if key not in cache:
            try:
                line = ask(client, *key)
            except Exception as e:  # 원인만 보고하고 중단 (자동 재시도 안 함)
                print(f"[{i}] {d['dept']} {d['doctor']} 실패: {type(e).__name__}: {e}")
                return 1
            terms = [] if line in ("없음", "없음.") else \
                clean_terms([t.strip(" .·\"'") for t in line.replace("，", ",").split(",") if t.strip(" .·\"'")])
            cache[key] = terms
            print(f"[{len(cache):3}] {d['dept']} | {d.get('specialty', '')[:30]} → {', '.join(terms) or '없음'}")
        rows.append({"dept": d["dept"], "doctor": d["doctor"], "specialty": d.get("specialty", ""),
                     "lay_terms": cache[key], "reviewed": False})

    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=1)
    write_csv(rows)
    print("=" * 70)
    print(f"의료진 {len(rows)}명, LLM 호출 {len(cache)}회, '없음' {sum(1 for r in rows if not r['lay_terms'])}명")
    print(f"저장: {OUT_JSON}, {OUT_CSV}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
