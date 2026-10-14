# POC 챗봇 사내 서버 배포 (docker compose)

사내 서버에 **POC 챗봇 컨테이너 하나만** 새로 추가한다. 이미 돌고 있는 서비스는 수정·재시작·삭제하지 않는다.

```
docker/chatpoc/
├─ docker-compose.yml   독립 프로젝트(chatpoc), 서비스 chatbot, 컨테이너 chatpoc-chatbot, 네트워크 chatpoc_net
├─ Dockerfile           화면 빌드 + FastAPI(화면과 API를 한 서버가 제공)
├─ .env.example         설정 예시 → 서버에서 .env 로 복사해 채운다
└─ .env                 (서버에서 직접 만든다. 저장소에 올라가지 않는다)
```

## 서버 작업 원칙 (반드시 지킨다)

이 서버에서 작업하는 사람과 AI 에이전트 모두에게 적용한다. 아래 문장은 그대로 작업 지침으로 쓴다.

> 기존 서비스는 절대 중지·삭제·재생성하지 않습니다. docker compose down, 전체 docker compose up -d 등의 명령은 사용하지 마십시오. 새로운 서비스가 필요한 경우 기존 compose 설정을 확인한 후 필요한 서비스만 추가하고, 해당 서비스만 기동하십시오. 기존 서비스의 설정이나 컨테이너에 영향을 주는 변경이 필요한 경우 반드시 먼저 확인하십시오

이 원칙을 이 문서의 절차에 이렇게 적용했다.

| 원칙 | 적용 |
|---|---|
| 기존 서비스를 중지·삭제·재생성하지 않는다 | 독립 프로젝트(`chatpoc`)·전용 컨테이너·전용 네트워크·볼륨 없음. 기존 컨테이너와 이름·네트워크를 공유하지 않는다 |
| `docker compose down`, 전체 `up -d` 금지 | 이 문서의 절차에는 두 명령이 실행 항목으로 나오지 않는다(금지 목록에만 있다). 기동은 **항상 서비스 이름을 지정**(`up -d --no-deps chatbot`), 중지는 `stop chatbot` |
| 기존 compose 설정을 확인한 뒤 필요한 서비스만 추가 | 0단계에서 기존 설정을 **읽기만** 한다. 추가하는 서비스는 `chatbot` 하나 |
| 영향이 있는 변경은 먼저 확인 | 아래 "먼저 확인받을 것"에 해당하면 **작업을 멈추고** 확인받는다 |

### 먼저 확인받을 것 (임의로 진행하지 않는다)
- 포트가 겹쳐서 기존 서비스의 포트를 바꿔야 하는 경우 (바꾸는 쪽은 항상 **새 서비스**의 `CHATPOC_PORT`다)
- 기존 compose 파일·기존 `.env`·기존 네트워크·기존 리버스 프록시(nginx 등) 설정을 수정해야 하는 경우
- 기존 컨테이너를 재시작하거나 다시 만들어야 하는 경우 (compose가 "recreate"를 표시하는 경우 포함)
- 방화벽·호스트 설정 변경이 필요한 경우
- 디스크·메모리 여유가 부족해 보이는 경우

## 아이디·비밀번호·서버 주소를 적는 곳

**`docker/chatpoc/.env`** — 이 파일 하나뿐이다. `.env.example`을 복사해서 서버에서 직접 채운다.

| 항목 | 변수 | 필수 | 설명 |
|---|---|---|---|
| LLM 서버 주소 | `LLM_BASE_URL` | 필수 | 예: `http://<IP>:<포트>/v1` (컨테이너 안에서 접속하므로 `localhost`가 아니라 실제 IP) |
| 모델 이름 | `LLM_MODEL` | 필수 | LLM 서버가 `/v1/models`로 알려 주는 `id` 그대로 |
| 대체 모델 | `LLM_FALLBACK_BASE_URL`, `LLM_FALLBACK_MODEL` | 선택 | 1순위가 실패하면 사용 |
| **LLM API 키** | `LLM_API_KEY` | 선택 | LLM 서버가 키를 요구할 때만 |
| **챗봇 접속 아이디** | `CHATBOT_BASIC_USER` | 선택 | 아이디·비밀번호를 **둘 다** 채우면 접속 시 로그인 창이 뜸 |
| **챗봇 접속 비밀번호** | `CHATBOT_BASIC_PASSWORD` | 선택 | 비우면 사내망에서 누구나 접속 |
| 열 포트 | `CHATPOC_PORT` | 선택 | 기본 `18080`. 서버에서 이미 쓰는 포트면 바꾼다 |

- 아이디·비밀번호·키는 **저장소·이미지·로그 어디에도 남지 않는다.** `.env`(권한 600)와 컨테이너 환경변수에만 있다.
- `.env` 값에는 따옴표를 붙이지 않는다.
- IP 가 확정되기 전에는 `.env.example`의 `<...>`를 그대로 두면 된다. 값이 비어 있으면 챗봇은 LLM 없이 키워드 규칙으로 동작한다.

## 기존 서비스에 영향이 없는 이유

| 항목 | 설정 |
|---|---|
| compose 프로젝트 | `name: chatpoc` — 다른 프로젝트와 이름이 다르다. 이 폴더의 `docker compose` 명령은 이 프로젝트의 컨테이너만 대상으로 한다 |
| 컨테이너·이미지 이름 | `chatpoc-chatbot`, `chatpoc/chatbot` — 기존 이름과 겹치지 않는다 |
| 네트워크 | `chatpoc_net`을 새로 만든다. 기존 네트워크에 붙지 않고 기존 컨테이너와 통신하지 않는다 |
| 호스트 포트 | 기본 18080 (바꿀 수 있음) |
| 볼륨 | 없다. 기존 데이터를 마운트하지 않는다 |
| 자원 | 메모리 512MB, 프로세스 256개 제한. 읽기 전용 파일시스템, 모든 권한 제거(`cap_drop: ALL`), 일반 사용자로 실행 |

## 배포 순서

모든 명령은 **서버의 `docker/chatpoc` 폴더**에서 실행한다.

### 0. 기존 설정 확인 (읽기만 한다 — 아무것도 바꾸지 않는다)
```bash
docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Ports}}\t{{.Status}}'   # 실행 중인 컨테이너와 포트
docker compose ls                                                            # 기존 compose 프로젝트 목록
docker network ls                                                            # chatpoc_net 이 이미 있는지
df -h /var/lib/docker; free -h                                               # 디스크·메모리 여유
```
기존 서비스의 compose 파일 위치와 서비스 목록은 이 읽기 명령으로 본다(파일을 열기만 하고 수정하지 않는다).
```bash
docker inspect --format '{{ index .Config.Labels "com.docker.compose.project.config_files" }}' <기존 컨테이너 이름>
docker compose -f <위에서 나온 기존 compose 파일> config --services
```
- 기존 컨테이너가 `18080`을 쓰고 있으면 `.env`의 `CHATPOC_PORT`를 다른 번호로 정한다.
- 같은 서버에 `chatpoc-chatbot` 컨테이너나 `chatpoc_net` 네트워크가 이미 있으면 **중단**하고 확인받는다.
- 위 "먼저 확인받을 것"에 해당하는 항목이 보이면 여기서 멈춘다.

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
docker compose config --services      # chatbot 한 줄만 나와야 한다
docker compose config                 # 프로젝트 이름 chatpoc, 포트·환경변수 확인
```

### 4. 이 서비스만 빌드하고 시작
```bash
docker compose up -d --build --no-deps chatbot
```
- **서비스 이름(`chatbot`)을 반드시 지정**한다. 서비스 이름 없이 `docker compose up -d`를 실행하지 않는다.
- 새 이미지와 컨테이너 `chatpoc-chatbot`만 만들어진다. 다른 컨테이너에는 아무 일도 일어나지 않는다.
- 출력에 `chatpoc-chatbot` 이외의 컨테이너 이름이 "Recreate/Stopping"으로 나오면 즉시 중단하고 확인받는다.
- 첫 빌드는 인터넷(Docker Hub, npm, PyPI)이 필요하다. 서버가 외부에 나갈 수 없다면 아래 "인터넷이 없는 서버" 참고.

### 5. 확인
```bash
docker compose ps                                       # STATUS 가 healthy 인지
curl -s http://127.0.0.1:18080/health                   # {"status":"ok"}
curl -s -u '<아이디>:<비밀번호>' http://127.0.0.1:18080/v1/config   # llmRouting 이 true 인지
docker compose logs --tail 50 chatbot                   # LLM 호출 실패 로그가 없는지
docker ps --format 'table {{.Names}}\t{{.Status}}'      # 기존 컨테이너의 가동 시간이 그대로인지
```
브라우저에서 `http://<서버 IP>:<CHATPOC_PORT>/` 로 접속해 질문을 입력해 본다.
(예: "차는 어디에 세우면 되나요" → 주차 안내로 이동하면 LLM이 동작하는 것)

## 운영

### 새 버전 반영
```bash
cd /opt/chatpoc && git pull
cd docker/chatpoc && docker compose up -d --build --no-deps chatbot
```
`.env`는 그대로 쓰이고, 챗봇 컨테이너만 교체된다.

### 설정(.env)만 바꿀 때
```bash
docker compose up -d --no-deps chatbot     # .env 가 바뀌었으면 챗봇 컨테이너만 다시 만든다
```

### 중지
```bash
docker compose stop chatbot                # 챗봇만 잠시 중지 (다시 시작: docker compose start chatbot)
```

### 이 서비스만 제거해야 할 때 (먼저 확인받는다)
```bash
docker compose rm -sf chatbot              # chatpoc-chatbot 컨테이너 하나만 제거
```
- `docker compose down`은 쓰지 않는다. 이 서비스를 더 이상 쓰지 않을 때만, 확인을 받은 뒤 위 명령을 쓴다.

### 하지 말 것
- `docker compose down` (옵션 무관), `docker compose down --remove-orphans`
- 서비스 이름 없는 `docker compose up -d` — 이 폴더에서는 결과가 같더라도 습관으로도 쓰지 않는다
- `docker system prune`, `docker container prune`, `docker network prune`, `docker volume prune` — 기존 서비스가 쓰는 자원을 지울 수 있다
- 기존 서비스의 compose 파일이 있는 폴더에서 이 파일을 실행하거나, `-p` 옵션으로 다른 프로젝트 이름을 덧씌우는 것
- 기존 컨테이너를 `docker stop`/`docker restart`/`docker rm` 하는 것

## 기존 compose 파일에 서비스를 추가해야 하는 경우 (예외 — 먼저 확인받는다)

운영 방침상 기존 compose 파일에 서비스를 합쳐야 한다면, **기존 설정을 확인한 뒤 `chatbot` 서비스 블록만 추가**하고 그 서비스만 기동한다. 기존 서비스 블록은 한 글자도 바꾸지 않는다.

```yaml
# 기존 compose 파일의 services: 아래에 이 블록만 추가한다
  chatpoc-chatbot:
    container_name: chatpoc-chatbot
    image: chatpoc/chatbot:latest
    build:
      context: /opt/chatpoc                       # 저장소를 받은 위치
      dockerfile: docker/chatpoc/Dockerfile
    restart: unless-stopped
    env_file:
      - /opt/chatpoc/docker/chatpoc/.env
    ports:
      - "18080:8000"                               # 기존 포트와 겹치지 않는 값
    networks:
      - chatpoc_net                                # 아래 networks: 에 새로 추가 (기존 네트워크에 붙지 않는다)
    read_only: true
    tmpfs: [/tmp]
    cap_drop: [ALL]
    security_opt: ["no-new-privileges:true"]
    mem_limit: 512m
# networks: 아래에 이 항목만 추가
  chatpoc_net:
    name: chatpoc_net
```
```bash
docker compose -f <기존 compose 파일> config --services     # 기존 서비스 + chatpoc-chatbot 이 보이는지 (읽기)
docker compose -f <기존 compose 파일> up -d --no-deps chatpoc-chatbot
```
- 같은 compose 프로젝트라도 `--no-deps`와 서비스 이름을 지정해 새 서비스만 만든다.
- 이 방식은 기존 파일을 수정하므로 **반드시 먼저 확인받은 뒤** 진행한다. 독립 프로젝트 방식(위 배포 순서)이 기본이다.

## 문제 해결

| 증상 | 확인 |
|---|---|
| `bind: address already in use` | `CHATPOC_PORT`가 이미 사용 중이다. `.env`에서 **새 서비스의** 포트를 바꾸고 `docker compose up -d --no-deps chatbot` |
| `env file .env not found` | 2단계를 하지 않았다. `cp .env.example .env` |
| 화면은 열리는데 질문이 계속 규칙으로만 처리된다 | `docker compose logs chatbot`에서 `LLM 호출 실패` 확인. `LLM_BASE_URL`·`LLM_MODEL`이 비어 있거나 `<...>` 그대로인지, 서버(호스트)에서 LLM 주소에 닿는지 확인 |
| 접속하면 로그인 창이 뜬다 | `CHATBOT_BASIC_USER/PASSWORD`가 설정돼 있다. 정상 동작이다 |
| 로그인 창이 안 뜨고 누구나 접속된다 | 아이디·비밀번호 중 하나가 비어 있다 (둘 다 있어야 켜진다) |
| `unhealthy` | `docker compose logs chatbot`로 시작 오류 확인. `.env`에서 `SITE_DIR`을 바꾸지 않았는지 확인 |
| 이미지 빌드 중 다운로드 실패 | 서버가 외부 인터넷에 나갈 수 없다. 아래 참고 |

### 인터넷이 없는 서버
인터넷이 되는 PC에서 이미지를 만들어 파일로 옮긴다.
```bash
# 인터넷이 되는 PC (저장소 루트에서)
docker build -f docker/chatpoc/Dockerfile -t chatpoc/chatbot:latest .
docker save chatpoc/chatbot:latest | gzip > chatpoc-chatbot.tar.gz

# 서버
gunzip -c chatpoc-chatbot.tar.gz | docker load
cd /opt/chatpoc/docker/chatpoc && docker compose up -d --no-build --no-deps chatbot
```
또는 사내 npm/PyPI 미러가 있으면 `.env`의 `NPM_REGISTRY`, `PIP_INDEX_URL`에 주소를 적는다.

## 보안 참고
- 이 구성은 **사내망 내부 사용**을 가정한다. 접속 시 아이디/비밀번호를 쓰더라도 http 는 평문이므로, 실제 사용자가 쓰는 서비스라면 리버스 프록시에서 https 를 종료하는 구성을 따로 검토한다.
- 질문 문장은 서버 로그에 남기지 않는다(기능 이름과 걸린 시간만 기록).
- 비밀번호·키 값은 저장소에 커밋하지 않는다. `.env`와 `*.local.*`은 `.gitignore`·`.dockerignore` 대상이다.
