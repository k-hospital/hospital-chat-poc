# POC 챗봇 사내 서버 배포 (docker compose)

사내 서버에 **POC 챗봇 컨테이너 하나만** 새로 추가한다. 이미 돌고 있는 컨테이너는 수정·재시작·삭제하지 않는다.

```
docker/chatpoc/
├─ docker-compose.yml   독립 프로젝트(chatpoc), 컨테이너 chatpoc-chatbot, 네트워크 chatpoc_net
├─ Dockerfile           화면 빌드 + FastAPI(화면과 API를 한 서버가 제공)
├─ .env.example         설정 예시 → 서버에서 .env 로 복사해 채운다
└─ .env                 (서버에서 직접 만든다. 저장소에 올라가지 않는다)
```

## 아이디·비밀번호·서버 주소를 적는 곳

**`docker/chatpoc/.env`** — 이 파일 하나뿐이다. `.env.example`을 복사해서 서버에서 직접 채운다.

| 항목 | 변수 | 필수 | 설명 |
|---|---|---|---|
| LLM 서버 주소 | `LLM_BASE_URL` | 필수 | 예: `http://<IP>:<포트>/v1` (컨테이너 안에서 접속하므로 `localhost`가 아니라 실제 IP) |
| 모델 이름 | `LLM_MODEL` | 필수 | LLM 서버가 제공하는 모델 이름 |
| 대체 모델 | `LLM_FALLBACK_BASE_URL`, `LLM_FALLBACK_MODEL` | 선택 | 1순위가 실패하면 사용 |
| **LLM API 키** | `LLM_API_KEY` | 선택 | LLM 서버가 키를 요구할 때만 |
| **챗봇 접속 아이디** | `CHATBOT_BASIC_USER` | 선택 | 아이디·비밀번호를 **둘 다** 채우면 접속 시 로그인 창이 뜸 |
| **챗봇 접속 비밀번호** | `CHATBOT_BASIC_PASSWORD` | 선택 | 비우면 사내망에서 누구나 접속 |
| 열 포트 | `CHATPOC_PORT` | 선택 | 기본 `18080`. 서버에서 이미 쓰는 포트면 바꾼다 |

- 아이디·비밀번호·키는 **저장소·이미지·로그 어디에도 남지 않는다.** `.env`(권한 600)와 컨테이너 환경변수에만 있다.
- `.env` 값에는 따옴표를 붙이지 않는다.
- IP 가 확정되기 전에는 `.env.example`의 `<...>`를 그대로 두면 된다. 값이 비어 있으면 챗봇은 LLM 없이 키워드 규칙으로 동작한다.

## 기존 컨테이너에 영향이 없는 이유

| 항목 | 설정 |
|---|---|
| compose 프로젝트 | `name: chatpoc` — 다른 프로젝트와 이름이 다르다. `docker compose` 명령은 이 프로젝트의 컨테이너만 대상으로 한다 |
| 컨테이너·이미지 이름 | `chatpoc-chatbot`, `chatpoc/chatbot` — 기존 이름과 겹치지 않는다 |
| 네트워크 | `chatpoc_net`을 새로 만든다. 기존 네트워크에 붙지 않고 기존 컨테이너와 통신하지 않는다 |
| 호스트 포트 | 기본 18080 (바꿀 수 있음) |
| 볼륨 | 없다. 기존 데이터를 마운트하지 않는다 |
| 자원 | 메모리 512MB, 프로세스 256개 제한. 읽기 전용 파일시스템, 모든 권한 제거(`cap_drop: ALL`), 일반 사용자로 실행 |

## 배포 순서

모든 명령은 **서버의 `docker/chatpoc` 폴더**에서 실행한다.

### 0. 사전 확인 (읽기만 한다)
```bash
docker ps --format 'table {{.Names}}\t{{.Ports}}'      # 쓰고 있는 포트 확인
docker network ls                                       # chatpoc_net 이 이미 있는지
```
- 기존 컨테이너가 `18080`을 쓰고 있으면 `.env`의 `CHATPOC_PORT`를 다른 번호로 정한다.
- 같은 서버에 `chatpoc-chatbot`이라는 컨테이너가 이미 있으면 중단하고 이름을 확인한다.

### 1. 코드 받기
기존 서비스 폴더와 **다른 위치**에 둔다 (예: `/opt/chatpoc`).
```bash
git clone https://github.com/k-hospital/hospital-chat-poc.git /opt/chatpoc
cd /opt/chatpoc/docker/chatpoc
```

### 2. 설정 파일 만들기
```bash
cp .env.example .env
chmod 600 .env
vi .env          # 위 표의 항목을 직접 채운다
```

### 3. 설정 검증 (아무것도 시작하지 않는다)
```bash
docker compose config
```
출력의 서비스가 `chatbot` 하나이고 프로젝트 이름이 `chatpoc`인지 확인한다.

### 4. 빌드하고 시작
```bash
docker compose up -d --build
```
- 새 이미지와 컨테이너 `chatpoc-chatbot`만 만들어진다. 다른 컨테이너에는 아무 일도 일어나지 않는다.
- 첫 빌드는 인터넷(Docker Hub, npm, PyPI)이 필요하다. 서버가 외부에 나갈 수 없다면 아래 "인터넷이 없는 서버" 참고.

### 5. 확인
```bash
docker compose ps                                       # STATUS 가 healthy 인지
curl -s http://127.0.0.1:18080/health                   # {"status":"ok"}
curl -s -u '<아이디>:<비밀번호>' http://127.0.0.1:18080/v1/config   # llmRouting 이 true 인지
docker compose logs --tail 50                           # LLM 호출 실패 로그가 없는지
```
브라우저에서 `http://<서버 IP>:<CHATPOC_PORT>/` 로 접속해 질문을 입력해 본다.
(예: "차는 어디에 세우면 되나요" → 주차 안내로 이동하면 LLM이 동작하는 것)

## 운영

### 새 버전 반영
```bash
cd /opt/chatpoc && git pull
cd docker/chatpoc && docker compose up -d --build
```
`.env`는 그대로 쓰이고, 챗봇 컨테이너만 교체된다.

### 설정(.env)만 바꿀 때
```bash
docker compose up -d        # .env 가 바뀌었으면 챗봇 컨테이너만 다시 만든다
```

### 중지 / 제거
```bash
docker compose stop         # 잠시 중지
docker compose down         # chatpoc 프로젝트의 컨테이너·네트워크만 제거 (다른 컨테이너는 그대로)
```

### 하지 말 것
- `docker compose down --remove-orphans` — 같은 프로젝트에 속하지 않은 컨테이너까지 지울 수 있다.
- `docker system prune`, `docker container prune`, `docker network prune`, `docker volume prune` — 기존 서비스가 쓰는 자원을 지울 수 있다.
- 기존 서비스의 compose 파일이 있는 폴더에서 이 파일을 실행하거나, `-p` 옵션으로 다른 프로젝트 이름을 덧씌우는 것.
- 기존 `docker-compose.yml`에 이 서비스를 합치는 것 (기존 프로젝트의 재생성 위험).

## 문제 해결

| 증상 | 확인 |
|---|---|
| `bind: address already in use` | `CHATPOC_PORT`가 이미 사용 중이다. `.env`에서 다른 포트로 바꾸고 `docker compose up -d` |
| `env file .env not found` | 2단계를 하지 않았다. `cp .env.example .env` |
| 화면은 열리는데 질문이 계속 규칙으로만 처리된다 | `docker compose logs`에서 `LLM 호출 실패` 확인. `LLM_BASE_URL`·`LLM_MODEL`이 비어 있거나 `<...>` 그대로인지, 서버에서 LLM 주소에 닿는지 (`docker compose exec`는 읽기 전용 이미지라 `curl`이 없으면 서버 호스트에서 확인) |
| 접속하면 로그인 창이 뜬다 | `CHATBOT_BASIC_USER/PASSWORD`가 설정돼 있다. 정상 동작이다 |
| 로그인 창이 안 뜨고 누구나 접속된다 | 아이디·비밀번호 중 하나가 비어 있다 (둘 다 있어야 켜진다) |
| `unhealthy` | `docker compose logs`로 시작 오류 확인. 대부분 `.env`의 `SITE_DIR`을 바꾼 경우 (바꾸지 않는다) |
| 이미지 빌드 중 다운로드 실패 | 서버가 외부 인터넷에 나갈 수 없다. 아래 참고 |

### 인터넷이 없는 서버
인터넷이 되는 PC에서 이미지를 만들어 파일로 옮긴다.
```bash
# 인터넷이 되는 PC (저장소 루트에서)
docker build -f docker/chatpoc/Dockerfile -t chatpoc/chatbot:latest .
docker save chatpoc/chatbot:latest | gzip > chatpoc-chatbot.tar.gz

# 서버
gunzip -c chatpoc-chatbot.tar.gz | docker load
cd /opt/chatpoc/docker/chatpoc && docker compose up -d --no-build
```
또는 사내 npm/PyPI 미러가 있으면 `.env`의 `NPM_REGISTRY`, `PIP_INDEX_URL`에 주소를 적는다.

## 보안 참고
- 이 구성은 **사내망 내부 사용**을 가정한다. 접속 시 아이디/비밀번호를 쓰더라도 http 는 평문이므로, 실제 사용자가 쓰는 서비스라면 리버스 프록시에서 https 를 종료하는 구성을 따로 검토한다.
- 질문 문장은 서버 로그에 남기지 않는다(기능 이름과 걸린 시간만 기록).
- 비밀번호·키 값은 저장소에 커밋하지 않는다. `.env`와 `*.local.*`은 `.gitignore`·`.dockerignore` 대상이다.
