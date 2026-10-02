# 병원 AI 상담 — 메인 화면 반영 코드

## 프론트 (React + TS, Vite)
- `src/features/home/` 폴더를 프로젝트에 복사
- 폰트: `index.html`에 추가
  `<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+KR:wght@400;500;600;700&display=swap">`

```tsx
import { MainScreen } from './features/home/MainScreen';
import { mockConfig } from './features/home/mockConfig';

<MainScreen
  config={mockConfig}            // 연결 후: GET /v1/config 응답
  handlers={{
    onAction: (m) => {/* POST /v1/chat/messages {type:"action", intent:m.intent} 후 대화 화면 전환 */},
    onSendText: (t) => {/* POST /v1/chat/messages {type:"text", text:t} 후 대화 화면 전환 */},
    onAgent: () => {/* POST /v1/handoff */},
    onCallback: () => {/* 콜백 대화 화면 */},
  }}
/>
```
- 테마 색: `.screen`의 `--accent` 값만 바꾸면 됨

## 백엔드 (FastAPI)
- `app/schemas/config.py`, `app/routers/config.py` 복사
- `main.py`: `app.include_router(config.router)`
- 응답은 camelCase(alias)라 프론트 `types.ts`와 그대로 맞음
