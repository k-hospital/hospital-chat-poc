import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import config

app = FastAPI(title="Hospital Chat POC")

# 프론트를 다른 도메인(Vercel 등)에 배포할 때 허용할 주소, 쉼표로 구분
origins = [o for o in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",") if o]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["*"], allow_headers=["*"])

app.include_router(config.router)


@app.get("/health")
def health():
    return {"status": "ok"}
