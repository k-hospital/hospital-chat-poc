"""
설정 — 모두 환경변수로 덮어쓸 수 있다 (기본값은 사내 개발 인프라).
설정 이름은 hospital_chatbot_poc/main.py와 같은 것은 같은 이름을 쓴다.
"""

from __future__ import annotations

import os

# backend/.env 파일이 있으면 읽는다 (비밀번호·키를 명령줄에 쓰지 않기 위해 — 2026-10-13).
# 이미 설정된 환경변수가 .env보다 우선한다. .env는 .gitignore로 제외, 항목은 .env.example 참고.
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
except ImportError:   # python-dotenv 미설치 — 환경변수만 사용
    pass


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


# --- 검색 (RAG) ---
# 사내 서버 주소·모델 이름은 저장소(공개)에 적지 않는다 → .env 에서만 설정 (항목은 .env.example)
QDRANT_URL = _env("QDRANT_URL", "")
QDRANT_COLLECTION = _env("QDRANT_COLLECTION", "hospital_chunks")
DENSE_VECTOR_NAME = _env("DENSE_VECTOR_NAME", "text-dense")
SPARSE_VECTOR_NAME = _env("SPARSE_VECTOR_NAME", "text-sparse")

DENSE_EMBEDDING_URL = _env("DENSE_EMBEDDING_URL", "")
DENSE_EMBEDDING_MODEL = _env("DENSE_EMBEDDING_MODEL", "BAAI/bge-m3")
# 운영: GPU wrapper(.32:8083) / 예비: CPU(.31:8091) — 같은 값이라 주소만 바꾸면 된다
SPARSE_EMBEDDING_URL = _env("SPARSE_EMBEDDING_URL", "")
RERANKER_URL = _env("RERANKER_URL", "")

# 2026-10-06 검색 설정 비교(tests/check_symptom_hit.py --compare-settings) 결과로 후보 10→30, 리랭크에 키워드 포함.
#   외국어 증상 25건 의료진 적중: 현재(10,KO) en 22·zh 23 → (30,KO+KW) en 25·zh 25, 일반 안내 저하 없음.
#   리랭커가 "손목"만 보면 "수부외과" 전문의 조각을 꼴찌로 보내던 문제 (tests/trace_doctor_search.py)
HYBRID_SEARCH_LIMIT = int(_env("HYBRID_SEARCH_LIMIT", "30"))
RERANK_TOP_N = int(_env("RERANK_TOP_N", "5"))
RERANK_WITH_KEYWORDS = _env("RERANK_WITH_KEYWORDS", "1") == "1"   # 리랭크 질문 = 번역문 + 검색 키워드
# Qwen3.6은 컨텍스트가 넓어서 한국어 챗봇(1,500/4,500자)보다 넉넉하게 준다
MAX_CHUNK_CHARS = int(_env("MAX_CHUNK_CHARS", "3000"))
MAX_CONTEXT_CHARS = int(_env("MAX_CONTEXT_CHARS", "12000"))

# --- 외국어 LLM (Qwen3.6 35B) ---
LLM_BASE_URL = _env("LLM_BASE_URL", "").rstrip("/")
LLM_MODEL = _env("LLM_MODEL", "")
LLM_API_KEY = _env("LLM_API_KEY", "")          # 사내 LLM은 인증 없음. 필요해지면 .env에만 넣는다
LLM_ANSWER_MAX_TOKENS = int(_env("LLM_ANSWER_MAX_TOKENS", "1024"))
LLM_TIMEOUT_SECONDS = float(_env("LLM_TIMEOUT_SECONDS", "90"))

# --- 한국어 LLM (카카오 카나나 2 3B, 8k) — /v1/chat 한국어 답변 ---
# 컨텍스트가 8k라 참고 자료 한도는 POC(main.py)와 같은 1,500/4,500자
KO_LLM_BASE_URL = _env("KO_LLM_BASE_URL", "").rstrip("/")
KO_LLM_MODEL = _env("KO_LLM_MODEL", "")
KO_LLM_API_KEY = _env("KO_LLM_API_KEY", "")
KO_LLM_ANSWER_MAX_TOKENS = int(_env("KO_LLM_ANSWER_MAX_TOKENS", "1024"))
KO_LLM_TIMEOUT_SECONDS = float(_env("KO_LLM_TIMEOUT_SECONDS", "60"))
KO_MAX_CHUNK_CHARS = int(_env("KO_MAX_CHUNK_CHARS", "1500"))
KO_MAX_CONTEXT_CHARS = int(_env("KO_MAX_CONTEXT_CHARS", "4500"))
# 1이면 한국어 질문도 Qwen3.6으로 검색 키워드를 확장 (호출 1회 추가). 측정 후 결정 — 기본 끔
KO_EXPAND_KEYWORDS = _env("KO_EXPAND_KEYWORDS", "0") == "1"
# 자료에 없는 내용(진료 일정 등)을 물을 때 안내할 대표전화 (홈페이지 기준)
HOSPITAL_PHONE = _env("HOSPITAL_PHONE", "1600-8291")

# --- 상담원 연결 (국내 전용) · 콜백 ---
HANDOFF_OPEN = _env("HANDOFF_OPEN", "08:30")                  # 상담 가능 시작 (HH:MM)
HANDOFF_CLOSE = _env("HANDOFF_CLOSE", "17:30")
HANDOFF_WEEKDAYS = {int(x) for x in _env("HANDOFF_WEEKDAYS", "0,1,2,3,4").split(",") if x.strip()}   # 0=월
HANDOFF_HOURS_TEXT = _env("HANDOFF_HOURS_TEXT", "평일 08:30 – 17:30")
HANDOFF_ALWAYS_OPEN = _env("HANDOFF_ALWAYS_OPEN", "0") == "1"   # 테스트용: 운영시간 무시
HANDOFF_MAX_CHATS_PER_AGENT = int(_env("HANDOFF_MAX_CHATS_PER_AGENT", "10"))
HANDOFF_GRACE_SECONDS = int(_env("HANDOFF_GRACE_SECONDS", "60"))   # 연결이 끊겨도 이 시간 안에 다시 붙으면 이어짐
HANDOFF_MAX_TRANSCRIPT = int(_env("HANDOFF_MAX_TRANSCRIPT", "20"))  # 상담원에게 넘기는 챗봇 대화 최대 줄 수
AGENT_PASSWORD = _env("AGENT_PASSWORD", "")                      # 비어 있으면 상담원 로그인 불가
AGENT_SESSION_HOURS = int(_env("AGENT_SESSION_HOURS", "12"))
CALLBACK_DB = _env("CALLBACK_DB", "callbacks.db")
CALLBACK_RETENTION_DAYS = int(_env("CALLBACK_RETENTION_DAYS", "7"))

# --- 음성인식 (Whisper, speaches) ---
STT_URL = _env("STT_URL", "")
STT_MODEL = _env("STT_MODEL", "")
STT_TIMEOUT_SECONDS = float(_env("STT_TIMEOUT_SECONDS", "60"))
MAX_AUDIO_BYTES = int(_env("MAX_AUDIO_BYTES", str(2 * 1024 * 1024)))   # 약 30초 녹음이면 충분
MAX_AUDIO_SECONDS = int(_env("MAX_AUDIO_SECONDS", "30"))                # 화면 녹음 제한 (안내용)

# --- 언어 ---
# 몽골어는 prompts.LANGS에 문구가 있지만, 품질 검증 전이라 기본 지원 목록에는 넣지 않는다.
SUPPORTED_LANGS = [x.strip() for x in _env("SUPPORTED_LANGS", "en,zh").split(",") if x.strip()]
DEFAULT_LANG = _env("DEFAULT_LANG", "en")

# --- 입력 제한·보안 ---
MAX_MESSAGE_CHARS = int(_env("MAX_MESSAGE_CHARS", "500"))
RATE_LIMIT_PER_MINUTE = int(_env("RATE_LIMIT_PER_MINUTE", "20"))      # IP당, 0이면 끔
CORS_ORIGINS = [x.strip() for x in _env("CORS_ORIGINS", "http://localhost:5173").split(",") if x.strip()]
ENABLE_DOCS = _env("ENABLE_DOCS", "0") == "1"                          # 개발 중에만 /docs
HTTP_TIMEOUT_SECONDS = float(_env("HTTP_TIMEOUT_SECONDS", "30"))

# 국제진료센터 안내 (홈페이지 '국제진료센터 > 소개' 페이지 기준. 전화번호는 확인 후 설정)
INTL_CENTER_CONTACT = _env("INTL_CENTER_CONTACT", "International Healthcare Center (E-mail: ish2014feb@gmail.com)")
