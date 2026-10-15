"""
의료진 추천 회귀 테스트 — 증상 부위에 맞는 전문의를 추천하는지, 다른 부위 전문의를 추천하지 않는지 본다.

실행 중인 백엔드(/v1/chat/foreign)에 부위별 증상 질문(영어·중국어)을 보내고, 답변의 한국어 병기 이름으로 판정:
  맞음  = 기대 전문의 중 1명 이상 언급
  오추천 = 다른 부위 전문의(wrong) 언급
  (이름 없이 진료과만 안내한 경우는 '추천 없음'으로 따로 센다)

기준 데이터: hospital_chatbot/data/ish_doctors.json (정형외과 전문분야)

실행:
    (백엔드) cd hospital-chat-poc\\ai-backend; $env:RATE_LIMIT_PER_MINUTE='0'; python -m uvicorn app:app --host 127.0.0.1 --port 8100
    (테스트) python check_doctor_recommend.py [--repeat 2]
"""

from __future__ import annotations

import argparse
import sys
import time

import httpx

ORTHO = ["이수빈", "오상윤", "조원민", "정환용", "채동식", "박희완", "이현희", "송명근", "김상희", "전병훈"]

CASES = [
    # (lang, 질문, 기대 전문의(이 중 1명 이상), 부위)
    ("en", "My wrist hurts.", ["김상희"], "손목"),
    ("zh", "我的手腕疼。", ["김상희"], "손목"),
    ("en", "My knee hurts when I walk.", ["전병훈", "정환용", "이현희", "채동식"], "무릎"),
    ("zh", "走路时膝盖疼。", ["전병훈", "정환용", "이현희", "채동식"], "무릎"),
    ("en", "I sprained my ankle.", ["송명근"], "발목"),
    ("zh", "我扭伤了脚踝。", ["송명근"], "발목"),
    ("en", "My shoulder hurts and I can't raise my arm.", ["오상윤"], "어깨"),
    ("zh", "肩膀疼，胳膊抬不起来。", ["오상윤"], "어깨"),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8100")
    ap.add_argument("--repeat", type=int, default=1)
    args = ap.parse_args()
    client = httpx.Client(timeout=180)

    right = wrong = none = total = 0
    for _ in range(args.repeat):
        for lang, q, expect, part in CASES:
            t = time.perf_counter()
            r = client.post(f"{args.base}/v1/chat/foreign", json={"message": q, "lang": lang})
            dt = time.perf_counter() - t
            if r.status_code != 200:
                print(f"[{lang}] {q} -> HTTP {r.status_code} {r.text[:100]}")
                continue
            ans = r.json()["answer"]
            named = [n for n in ORTHO if n in ans]
            bad = [n for n in named if n not in expect]
            good = [n for n in named if n in expect]
            total += 1
            if bad:
                wrong += 1
                mark = "X 오추천"
            elif good:
                right += 1
                mark = "O"
            else:
                none += 1
                mark = "- 추천없음"
            print(f"[{lang}] {mark:<6} {part:<3} 언급={named or '없음'}  {dt:.1f}s  {q}")
    print("=" * 70)
    print(f"맞는 전문의 {right}/{total}   다른 부위 전문의 언급 {wrong}   의료진 이름 없음 {none}")
    return 0 if wrong == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
