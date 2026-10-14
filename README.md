# 병원 AI 상담 챗봇 POC

## 프론트 실행 (React + TS, Vite)
```bash
cd frontend
npm install
npm run dev        # http://localhost:5173
```
- 백엔드가 없으면 목업 데이터로 화면이 표시됩니다.
- 야간 화면 확인: http://localhost:5173/?night=1

## 백엔드 실행 (FastAPI)
```bash
cd backend
python -m venv .venv
.venv\Scripts\activate          # Mac/Linux: source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload   # http://localhost:8000/docs
```
- 프론트 개발 서버는 /v1 요청을 8000번으로 자동 전달합니다.
- 테스트: `pip install -r requirements-dev.txt` 후 `python -m pytest` (사내 LLM 서버에는 요청을 보내지 않습니다)

## 사내 서버에 Docker로 배포
기존 컨테이너를 건드리지 않고 POC 챗봇 컨테이너 하나만 추가하는 compose 구성이 `docker/chatpoc/`에 있습니다. 서버 주소와 아이디/비밀번호는 서버의 `docker/chatpoc/.env`에만 적습니다. 절차는 [docker/chatpoc/README.md](docker/chatpoc/README.md)를 보세요.

## 사내 서버 실행 (질문을 LLM으로 분류 + 챗봇 화면 함께 제공)
사내 AI 서버(OpenAI 호환 API)에 닿는 PC 한 대에서 백엔드를 띄우면, 같은 주소로 챗봇 화면과 API를 함께 제공합니다. 직접 입력한 질문은 사내 LLM이 분류하고(여러 요청이면 최대 3개를 순서대로), 서버가 없거나 응답이 없으면 키워드 규칙으로 대체됩니다.

> **사내 서버 주소·모델 이름은 이 저장소(공개)에 적지 않습니다.** 실행하는 PC의 환경변수나 `*.local.ps1`/`*.local.json`(저장소에 올라가지 않는 파일)으로만 지정하세요.

```powershell
cd frontend
npm run build:site -- --out C:\chatpoc-site       # 공백 없는 경로, 도메인 루트(/chat/) 기준 빌드
cd ..\backend
pip install -r requirements.txt
copy run-server.example.ps1 run-server.local.ps1  # 복사본에 서버 주소·모델 이름을 채운다 (저장소에 올라가지 않음)
powershell -ExecutionPolicy Bypass -File .\run-server.local.ps1   # 팀원은 http://<이 PC 주소>:8080/ 로 접속
```

| 환경변수 | 기본값 | 설명 |
|---|---|---|
| `LLM_BASE_URL` / `LLM_MODEL` | (없음, 필수) | 질문 분류에 쓰는 1순위 모델의 OpenAI 호환 주소(`…/v1`)와 이름. 없으면 LLM 분류를 쓰지 않음 |
| `LLM_FALLBACK_BASE_URL` / `LLM_FALLBACK_MODEL` | (없음) | 1순위가 실패했을 때 쓰는 대체 모델 (비우면 사용 안 함) |
| `SITE_DIR` | (없음) | `build:site` 결과 폴더. 지정하면 화면까지 함께 제공 (없으면 API만) |
| `LLM_TIMEOUT_SECONDS` | `6` | 모델 한 번 호출의 제한 시간 |
| `LLM_ENABLED` | `1` | `0`이면 LLM 분류를 끄고 키워드 규칙만 사용 |
| `CORS_ORIGINS` | `http://localhost:5173` | 화면을 다른 주소에서 제공할 때만 필요 |
| `LOG_LEVEL` | `INFO` | 질문 문장은 로그에 남기지 않고 분류된 기능과 걸린 시간만 남깁니다 |

- 다른 PC에서 접속하려면 Windows 방화벽에서 해당 포트(8080)를 허용해야 합니다.
- 응급 신호는 서버를 기다리지 않고 챗봇이 규칙으로 먼저 안내합니다. LLM이 응급으로 판단한 경우도 같은 안내가 나옵니다.
- GitHub Pages 사이트에는 이 서버가 없으므로 키워드 규칙만 사용합니다(화면은 그대로 동작).

## 메인 화면 + 챗봇 묶음 배포 (GitHub Pages)
현재 운영 주소: https://k-hospital.github.io/hospital-chat-poc/

| 경로 (운영 주소 기준) | 내용 | 소스 |
|---|---|---|
| `/hospital-chat-poc/` | 메인 화면 (AI 상담 버튼으로 챗봇 열기) | `site/index.html` |
| `/hospital-chat-poc/chat/` | 챗봇 | `frontend/` |
| `/hospital-chat-poc/pages/...` | 챗봇 안에서 여는 연결 페이지 (오시는 길, 증상별 진료 안내) | `frontend/public/pages/` |

```bash
cd frontend
npm test              # 질문 판별기·추천 질문·엑셀 변환 테스트
npm run build:site    # → 저장소 루트의 deploy/ 폴더 생성 (커밋되지 않음), 로컬 확인용
```
- 다른 위치에 만들려면 `npm run build:site -- --out <폴더 경로>`
- 하위 경로용 빌드: `SITE_BASE=/hospital-chat-poc/ npm run build:site` (운영 빌드와 같은 설정)
- 배포는 자동: PR을 `main`에 머지하면 GitHub Actions(`.github/workflows/deploy.yml`)가 테스트 → 추천 질문 동기화 → 빌드 → Pages 배포를 실행합니다. 결과는 저장소 **Actions** 탭에서 확인하고, 수동 실행도 같은 탭에서 할 수 있습니다.
- 저장소 Settings → Pages → Source는 **GitHub Actions**여야 합니다.

## 배포 (분리 배포 시)
- 프론트(Vercel): Root Directory = `frontend`, 환경변수 `VITE_API_BASE` = 백엔드 주소(없으면 목업 표시)
- 백엔드(Render 등): Root Directory = `backend`, Dockerfile 사용, 환경변수 `CORS_ORIGINS` = 프론트 주소
