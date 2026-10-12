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
