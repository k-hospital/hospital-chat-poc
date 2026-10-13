# CLAUDE.md

병원 AI 상담 챗봇 POC. 메인 화면(병원 홈페이지형 샘플) + 챗봇을 한 사이트로 묶어 GitHub Pages에 배포한다.
작업 이력·기능 설명·해야 할 일은 [docs/작업정리.md](docs/작업정리.md)에 있다.

## 구조

| 경로 | 내용 |
|---|---|
| `site/index.html` | 메인 화면 (정적 HTML 한 파일). AI 상담 위젯이 챗봇을 iframe으로 연다. 배포 사이트에서는 같은 사이트의 `chat/`, 내 PC에서는 개발 서버, 개발 서버가 없으면 위젯 폴백(로컬용 대체 주소 `CHATBOT_URL`) |
| `frontend/` | 챗봇 (React 18 + TypeScript + Vite) |
| `frontend/public/pages/` | 챗봇 안에서 여는 연결 페이지 (오시는 길, 증상별 진료 안내) |
| `backend/` | FastAPI — `/v1/config`(설정), `POST /v1/chat/messages`(질문을 사내 LLM으로 분류, 최대 3개 기능). 사내 PC에서 실행(README "사내 서버 실행"), GitHub Pages에는 없음 → 프론트는 목업(`mockConfig.ts`)과 키워드 규칙으로 동작 |

프론트 주요 파일
- `src/App.tsx` — 화면 전환(메인 / 연결 페이지 / 설정), 질문 처리(`ask`), 메뉴 이동(`openLink`)
- `src/shared/ui/ChatInputBar.tsx` — 모든 화면 하단에 고정되는 공통 질문 입력 바
- `src/shared/chat/intentRouter.ts` — 질문 → 기능(intent) 키워드 판별. 응급 신호를 가장 먼저 검사
- `src/shared/chat/llmRouter.ts` — 직접 입력한 질문을 서버(`/v1/chat/messages`)로 분류. 실패하면 null → `App.ask`가 키워드 규칙으로 대체. 응급은 서버를 기다리지 않고 규칙이 먼저 처리한다
- `backend/app/features/chat/` — `intent_prompt.txt`·`intent_schema.json`(프롬프트와 출력 형식, 평가 스크립트도 같은 파일을 읽음), `service.py`(LLM 호출·검증·응급 우선·최대 3개), 질문 문장은 로그에 남기지 않는다
- `scripts/llm-eval/` — 모델 비교 평가(`npx vite-node scripts/llm-eval/run.ts`). 문항은 `cases.json`, 서버 주소는 `models.local.json`(예시: `models.example.json`). 프롬프트·모델을 바꾸면 다시 돌려 정확도를 확인한다
- `src/shared/chat/suggestions.ts` — 입력창 화면별 추천 질문. 목록 데이터는 `suggestions.json`(엑셀에서 생성)이고, 질문마다 연결 기능(intent)이 정해져 있어 누르면 키워드 판별기보다 그 기능이 우선한다(`routeSuggestion`). 응급 검사는 그대로 먼저 실행
- `src/shared/chat/suggestions.json` — **직접 수정하지 않는다.** `data/suggestions.xlsx`를 고친 뒤 `npm run sync:suggestions`로 다시 만든다
- `data/suggestions.xlsx` — 추천 질문 편집 원본. '추천질문' 시트(질문·화면·연결 기능·순서·사용)와 '목록' 시트(화면/연결 기능 선택지·내부 키). 형식·검증 규칙은 `scripts/suggestionsFromRows.mjs`
- `src/shared/links/linkStore.ts` — 기능별 연결 주소(localStorage) + 기본값(`DEFAULT_LINKS`)
- `src/features/page/PageViewer.tsx` — 연결 페이지를 챗봇 안 iframe으로 표시, 입력 문구는 postMessage로 같은 사이트에만 전달

## 명령어 (frontend/)

```bash
npm install
npm run dev                                  # http://localhost:5173
npm test                                     # Vitest (질문 판별기, 추천 질문, 엑셀 변환)
npm run sync:suggestions                     # data/suggestions.xlsx → src/shared/chat/suggestions.json
npm run sync:suggestions -- <엑셀 경로>       # 다른 위치의 엑셀로 생성 (검증 오류가 있으면 파일을 쓰지 않음)
npm run build                                # tsc -b + vite build
npm run build:site                           # 메인+챗봇 묶음 → <저장소>/deploy
npm run build:site -- --out <폴더>           # 다른 위치에 생성
SITE_BASE=/hospital-chat-poc/ npm run build:site   # 하위 경로(GitHub Pages)용 — 챗봇이 /hospital-chat-poc/chat/ 기준으로 빌드됨
```

`SITE_BASE`를 비우면 도메인 루트(`/chat/`)로 빌드된다 (로컬 확인이나 다른 호스팅용). 운영(GitHub Pages)은 `.github/workflows/deploy.yml`이 `SITE_BASE=/hospital-chat-poc/`로 빌드하며, 저장소 이름을 바꾸면 이 값도 함께 바꾼다.

## 추천 질문 편집 방법

1. `frontend/data/suggestions.xlsx`를 엑셀에서 고치고 저장한다 (한 번에 한 사람만). 화면·연결 기능·사용은 드롭다운에서 고르고, 순서는 1 이상의 정수.
2. `cd frontend && npm run sync:suggestions` — 오류가 있으면 어느 시트 몇 행인지 알려 주고 JSON은 바뀌지 않는다.
3. `npm test` 통과 확인 → `suggestions.xlsx`와 `suggestions.json`을 **함께** 커밋 (원본과 생성 결과가 어긋나지 않게).
4. 새 화면·연결 기능이 필요하면 '목록' 시트에 줄을 추가하고 내부 키는 코드의 기능 키와 같게 쓴다 (모르는 키는 `suggestions.test.ts`가 잡는다).
- 엑셀에서 '사용'으로 둔 질문은 연결 주소(⚙ 설정) 여부와 상관없이 모두 표시된다. 주소가 없는 기능의 질문을 누르면 "'기능명' 서비스는 준비중입니다"가 나온다 (예: 상담원 연결).

## 작업 순서 (팀 합의)

1. 새 브랜치에서 작업 → 테스트·타입검사 통과 확인 → 커밋·push
2. PR 생성 → 검토 → `main`에 머지
3. `main`에 머지되면 GitHub Actions(`Deploy to GitHub Pages`)가 테스트 → `sync:suggestions` → `build:site` → 배포를 자동 실행한다. 손으로 빌드·업로드하지 않는다
4. 저장소 **Actions** 탭에서 build·deploy가 모두 초록색인지 확인하고, 실제 주소 https://k-hospital.github.io/hospital-chat-poc/ 에서 확인

- 테스트가 실패하면 배포되지 않는다. 수동 재실행은 Actions → Deploy to GitHub Pages → Run workflow
- 되돌리기: 문제가 된 PR을 Revert하는 PR을 만들어 머지하면 이전 상태로 다시 배포된다
- 이전 Netlify 사이트(`ephemeral-parfait-e65ef8`)는 더 이상 갱신하지 않는다

## 주의

- 증상 관련 화면은 진단이 아니다. 면책 문구("AI 안내는 참고용이며 진단이 아닙니다")는 항상 노출한다.
- 응급 판별(`EMERGENCY`)은 다른 규칙·AI 판별보다 먼저 실행해야 한다.
- 증상 등 입력 문구를 URL 쿼리(`?q=`)에 넣지 않는다. 외부 사이트로 전달하지 않는다.
- 연결 페이지·메인 화면 데이터(병원명·주소·전화·노선)는 모두 가상 데이터다. 실제 기관 정보·로고를 넣지 않는다.
- Windows Git Bash에서 `vite build --base /chat/`처럼 `/`로 시작하는 인자는 경로로 변환되어 빌드가 깨진다 → `build:site` 스크립트(Vite API 직접 호출)를 쓴다.
- PowerShell 실행 정책 때문에 `npm`(npm.ps1)이 막히면 `npm.cmd` 또는 `node node_modules/...`로 직접 실행한다.
- 저장소는 **공개(Public)** 이다(무료 플랜에서 Pages를 쓰기 위해 전환). 비밀 값·API 키·실제 기관 정보·개인 연락처를 커밋하지 않는다. 한 번 올라간 기록은 지워도 남는다.
- **사내 서버 주소(IP)·모델 이름도 커밋하지 않는다.** 코드에는 기본값을 두지 않고 환경변수(`LLM_BASE_URL` 등)나 `*.local.ps1`/`*.local.json`(`.gitignore` 대상)으로만 받는다. push 전에 `git grep -nE "([0-9]{1,3}\.){3}[0-9]{1,3}:[0-9]{2,5}"`로 주소가 남았는지 확인한다.
- 저장소 루트의 `backend.zip`(node_modules 포함 스냅숏), `deploy/`, `production-site/`는 커밋하지 않는다.
- 연결 페이지 기본 주소(`DEFAULT_LINKS`)는 빌드된 base 기준으로 계산된다. ⚙ 설정에서 이미 저장한 브라우저는 저장값이 우선하므로, 배포 주소가 바뀌면 설정을 비워야 새 기본값이 적용된다.
