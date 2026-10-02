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

## 배포
- 프론트(Vercel): Root Directory = `frontend`, 환경변수 `VITE_API_BASE` = 백엔드 주소(없으면 목업 표시)
- 백엔드(Render 등): Root Directory = `backend`, Dockerfile 사용, 환경변수 `CORS_ORIGINS` = 프론트 주소
