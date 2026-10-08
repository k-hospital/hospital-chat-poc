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

## 메인 화면 + 챗봇 묶음 배포 (Netlify)
현재 운영 주소: https://ephemeral-parfait-e65ef8.netlify.app

| 경로 | 내용 | 소스 |
|---|---|---|
| `/` | 메인 화면 (AI 상담 버튼으로 챗봇 열기) | `site/index.html` |
| `/chat/` | 챗봇 | `frontend/` |
| `/pages/...` | 챗봇 안에서 여는 연결 페이지 (오시는 길, 증상별 진료 안내) | `frontend/public/pages/` |

```bash
cd frontend
npm test              # 질문 판별기 테스트
npm run build:site    # → 저장소 루트의 deploy/ 폴더 생성 (커밋되지 않음)
```
- 다른 위치에 만들려면 `npm run build:site -- --out <폴더 경로>`
- 순서: PR 머지 → 최신 `main`에서 `build:site` → 생성된 폴더를 Netlify 사이트의 **배포(Deploys)** 화면에 끌어다 놓기
- Netlify는 GitHub에 연결되어 있지 않으므로 머지만으로는 운영 주소가 바뀌지 않습니다.

## 배포 (분리 배포 시)
- 프론트(Vercel): Root Directory = `frontend`, 환경변수 `VITE_API_BASE` = 백엔드 주소(없으면 목업 표시)
- 백엔드(Render 등): Root Directory = `backend`, Dockerfile 사용, 환경변수 `CORS_ORIGINS` = 프론트 주소
