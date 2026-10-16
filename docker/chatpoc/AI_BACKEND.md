# ai-backend 배포 (음성인식 · 외국어 답변 · 상담원 연결)

`ai-backend/`(FastAPI, 8100)는 마이크 입력, 영어·중국어 답변, 상담원 연결·콜백을 맡는다. 이 문서는 사내 서버의 챗봇 컨테이너 옆에 **컨테이너를 하나 더** 두는 구성과, 켜기 전에 확인받을 것을 정리한다.

> **지금 상태: 준비만 되어 있고 꺼져 있다.** `.env`의 `AI_BACKEND_URL`이 비어 있으면 챗봇 컨테이너는 이 기능이 없을 때와 똑같이 동작하고, `ai-backend` 서비스는 만들어지지도 않는다(compose profile `ai`).

## 구성

```
브라우저 ──http(s)──> chatpoc-chatbot (8000 → 호스트 18080)
                        ├─ 화면(/, /chat/, /pages/)과 /v1/config, /v1/chat/messages 는 직접 처리
                        └─ /v1/stt, /v1/chat, /v1/handoff*, /v1/agent*, /v1/callbacks  ──프록시──>
                               chatpoc-ai-backend (8100, 호스트 포트 없음, chatpoc_net 안에서만)
                                  ├─ Qdrant · 임베딩(dense/sparse) · 리랭커   (검색)
                                  ├─ 외국어 LLM · 한국어 LLM                   (답변)
                                  ├─ Whisper                                  (음성인식)
                                  └─ /data/callbacks.db (볼륨 chatpoc_ai_data) (콜백 신청)
```

- 화면은 지금처럼 **주소 하나(18080)** 만 쓴다. 같은 출처라 CORS 설정이 필요 없다.
- 프록시는 `backend/app/ai_proxy.py`. 목록에 있는 경로(HTTP 10개, WebSocket 2개)만 넘기고, 팀 backend 경로는 건드리지 않는다.
- 접속자 IP 별 요청 제한(분당 POST 20회)은 프록시가 하고, ai-backend 쪽은 끈다(거기서 보이는 IP는 프록시뿐이라서).

## 켜기 전에 확인받을 것 (결정 사항)

| # | 확인 | 이유 |
|---|---|---|
| 1 | **https 적용 방법** (사내 인증서, 리버스 프록시 위치) | 마이크는 https/localhost에서만 동작한다. 상담원 화면의 공용 비밀번호도 http에서는 평문이다 |
| 2 | **콜백 전화번호 저장**을 이 서버에 해도 되는지 (개인정보 담당) | SQLite 볼륨에 전화번호가 7일간 저장된다 |
| 3 | **실제 병원 정보**가 든 프롬프트·검색 데이터를 이 저장소와 서버에 두어도 되는지 | `ai-backend/README.md`가 "가상 데이터만" 규칙과 다르다고 적고 있다. 대표전화 기본값도 실제 번호다 |
| 4 | **새 볼륨(`chatpoc_ai_data`)과 새 컨테이너**를 기존 서버에 추가해도 되는지 | 지금 챗봇은 "볼륨 없음"으로 격리되어 있다. 서버 작업 원칙의 "먼저 확인받을 것"에 해당한다 |

## 서버에 영향을 주는 것

| 대상 | 변경 |
|---|---|
| 새로 만들어짐 | 컨테이너 `chatpoc-ai-backend`, 이미지 `chatpoc/ai-backend`, 볼륨 `chatpoc_ai_data` |
| 다시 만들어짐 | `chatpoc-chatbot` (`AI_BACKEND_URL` 환경변수가 바뀌므로 한 번 교체됨) |
| 바뀌지 않음 | 기존 서비스·컨테이너·네트워크, 호스트 포트(새로 열지 않음) |

## 켜는 순서 (서버, `docker/chatpoc` 폴더에서)

모든 명령은 **서비스 이름을 지정**한다. `docker compose down`, 이름 없는 `up -d`는 쓰지 않는다.

**1. `.env`에 값 채우기** — `.env.example`의 "ai-backend" 구역(`AI_*`)을 채운다. 비밀번호·키는 서버의 `.env`에만 적는다.

**2. 서버에서 7곳에 닿는지 읽기 전용으로 확인**
```bash
set -a; . ./.env; set +a
for u in "$AI_QDRANT_URL/collections" "$AI_DENSE_EMBEDDING_URL" "$AI_SPARSE_EMBEDDING_URL" \
         "$AI_RERANKER_URL" "$AI_LLM_BASE_URL/models" "$AI_KO_LLM_BASE_URL/models" "$AI_STT_URL"; do
  printf '%s -> ' "$u"; curl -s -m 5 -o /dev/null -w '%{http_code}\n' "$u" || echo 연결실패
done
```
응답 코드가 나오면(404도 연결은 된 것) 정상이다. `연결실패`나 `000`이면 해당 서버로의 경로(방화벽·대역)를 먼저 해결한다.

**3. ai-backend만 빌드·기동** (챗봇은 그대로)
```bash
docker compose --profile ai up -d --build --no-deps ai-backend
docker compose --profile ai ps ai-backend            # healthy 확인
docker compose --profile ai logs --tail 30 ai-backend  # "설정 누락" 로그가 없어야 한다
```

**4. 챗봇이 ai-backend로 넘기도록 연결** — `.env`에서 `AI_BACKEND_URL=http://ai-backend:8100`로 바꾸고
```bash
docker compose up -d --no-deps chatbot
```

**5. 확인** (브라우저, https 또는 localhost 에서)
- 입력창에 영어 문장("Where is the parking lot?") → 영어 답변
- 마이크 버튼 → 녹음 → 문장 인식
- 상담원 연결 → 운영시간 안에서 상담원 화면(`/chat/?agent`)에 대기 알림이 오는지

## 되돌리기
```bash
# 1) .env 에서 AI_BACKEND_URL= (비움) 후
docker compose up -d --no-deps chatbot           # 챗봇이 예전처럼 동작
# 2) ai-backend 만 내리기 (볼륨의 콜백 데이터는 남는다)
docker compose --profile ai rm -sf ai-backend
```
콜백 데이터까지 지울 때만 `docker volume rm chatpoc_ai_data`(확인 후).

## 알아 둘 점
- **`.env`의 `AI_*` 값은 챗봇 컨테이너에도 환경변수로 들어간다.** `env_file: .env`가 파일 전체를 넘기기 때문이다(챗봇 코드는 읽지 않는다). 키·비밀번호를 챗봇 컨테이너에서 분리하려면 별도 파일로 나누는 후속 작업이 필요하다.
- **상담원 연결 가능 시간**은 서버의 `AI_HANDOFF_*`가 결정한다. 화면 ⚙ 설정의 "상담 운영시간"은 이 브라우저의 표시용 야간 화면 판단이며 서버 설정을 바꾸지 않는다.
- **상담 대기열·대화는 메모리에만** 있다(작업자 1개). ai-backend를 다시 만들면 진행 중인 상담이 끊긴다.
- **ai-backend는 호스트 포트를 열지 않는다.** 챗봇 컨테이너를 거치지 않고는 접근할 수 없다.
- 이 이미지는 아직 서버에서 **빌드해 본 적이 없다**. 프록시는 이 저장소의 시험(`backend/tests/test_ai_proxy.py`)과 실제 ai-backend와의 연동 시험으로 확인했지만, Dockerfile·compose 서비스는 첫 빌드에서 확인된다.
