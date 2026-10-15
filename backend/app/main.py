import logging
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.access import BasicAuthMiddleware
from app.features.chat.router import router as chat_router
from app.features.config.router import router as config_router
from app.static_site import CachedStaticFiles

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = FastAPI(title="Hospital Chat POC")

# 프론트를 다른 도메인(Vercel 등)에 배포할 때 허용할 주소, 쉼표로 구분
origins = [o for o in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",") if o]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["*"], allow_headers=["*"])

# CHATBOT_BASIC_USER / CHATBOT_BASIC_PASSWORD 가 설정된 경우에만 화면·API에 아이디/비밀번호를 요구한다
app.add_middleware(BasicAuthMiddleware)

app.include_router(config_router)
app.include_router(chat_router)


@app.get("/health")
def health():
    return {"status": "ok"}


# 사내에서 챗봇 화면까지 한 서버로 제공할 때: SITE_DIR=<npm run build:site 결과 폴더>
# 같은 주소에서 화면과 API(/v1)를 함께 주므로 CORS 설정이 필요 없다. API 라우트보다 뒤에 연결해야 한다.
_site_dir = os.getenv("SITE_DIR", "").strip()
if _site_dir:
    _site_path = Path(_site_dir)
    if not _site_path.is_dir():
        raise RuntimeError(f"SITE_DIR 폴더가 없습니다: {_site_path}")
    app.mount("/", CachedStaticFiles(directory=_site_path, html=True), name="site")
