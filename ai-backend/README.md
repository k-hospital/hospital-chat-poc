# ai-backend — 음성인식 · 외국어 답변 · 상담원 연결

팀 `backend/`(설정·질문 분류, 8000)와 **별도로 8100 포트**에서 실행한다. 화면 개발 서버(`frontend/vite.config.ts`)가
`/v1/config`·`/v1/chat/messages`는 8000으로, 나머지 `/v1`(아래 API)은 8100으로 나눠 보낸다.

## 언제 동작하나 (화면 기준)
| 동작 | 처리 |
|---|---|
| 마이크 버튼 | 녹음 → `POST /v1/stt`(사내 Whisper). 한국어면 입력과 같은 팀 흐름, 영어·중국어면 `POST /v1/chat`으로 그 언어 답변 |
| 외국어로 입력 (한글 없음) | `POST /v1/chat` → 번역+검색어 확장(Qwen3.6) → RAG → 그 언어로 답변 |
| 상담원 연결 / 콜백 요청 | `POST /v1/handoff` + WebSocket 실시간 대화(국내 전용). 상담원이 없거나 운영시간 외면 콜백 신청 |
| 상담원 화면 | 프론트 `…/agent` (또는 `?agent`) — 공용 비밀번호 로그인 |

## API
| 경로 | 설명 |
|---|---|
| `POST /v1/stt` | multipart `audio`(+`lang_hint`) → `{text, language, route}` |
| `POST /v1/chat` | `{message, lang?}` → `{lang, answer, sources, emergency, disclaimer, ...}` (한국어는 카나나 3B, 외국어는 Qwen3.6) |
| `POST /v1/chat/foreign` | 외국어 전용 (예전 경로, 유지) |
| `GET /v1/handoff/status`, `POST /v1/handoff`, `WS /v1/handoff/ws/{ticket}` | 이용자 상담원 연결 |
| `POST /v1/agent/login`, `WS /v1/agent/ws?token=`, `GET /v1/agent/callbacks` | 상담원 화면 |
| `POST /v1/callbacks` | 콜백 요청 (전화번호·희망 시간, 동의 필수) |

## 실행 (Windows PowerShell)
```powershell
cd ai-backend
pip install -r requirements.txt
copy .env.example .env      # AGENT_PASSWORD 입력, 운영시간 외 테스트는 HANDOFF_ALWAYS_OPEN=1
python -m uvicorn app:app --host 127.0.0.1 --port 8100
```
화면: `cd frontend; npm.cmd run dev` → 이용자 `http://localhost:5173`, 상담원 `http://localhost:5173/agent`
(팀 `backend/`도 8000으로 켜 두면 질문 분류까지 함께 동작)

## 데이터·개인정보 원칙
- 질문·음성·상담 대화는 **저장하지 않음** (상담 대화는 메모리에만, 종료 즉시 삭제). 로그에 본문 없음
- 콜백(전화번호)만 SQLite `callbacks.db` — 처리 완료 또는 7일 후 삭제, `.gitignore` 제외
- 비밀값은 `.env`에만. 화면 쪽 `VITE_*` 환경변수에 키를 넣지 않는다
- 사내 서버(Qdrant·임베딩·LLM·Whisper)에 접속하므로 사내망에서만 동작
- ⚠️ 프롬프트(`prompts.py`)와 검색 데이터는 실제 병원 정보를 사용 — 저장소 규칙("가상 데이터만")과 다르므로 팀 확인 필요

## 파일
`app.py`(라우트) · `config.py`(설정, `.env`) · `rag.py`(검색) · `prompts.py`(프롬프트·응급 규칙) · `translate.py`(언어 판별·LLM 호출) ·
`stt.py`(Whisper) · `handoff.py`(대기열·실시간 대화) · `callbacks.py`(콜백 DB) · `tests/`(검색·답변 품질 측정 스크립트)

문서: `docs/번역_음성인식_설계서.md`, `docs/프롬프트_정리.md`, `docs/데이터_파이프라인.md`
(이 문서들 안의 `hospital_chatbot/backend`, `global_chatbot` 경로는 이 저장소의 `ai-backend/`, 데이터 스크립트는 `data-pipeline/`)
