# syntax=docker/dockerfile:1
# 사내 서버용 이미지: 챗봇 화면(React)을 빌드해 FastAPI 서버가 화면과 API를 함께 제공한다.
# 빌드 컨텍스트는 저장소 루트다 (docker/chatpoc/docker-compose.yml 의 build.context).

ARG NODE_IMAGE=node:20-slim
ARG PYTHON_IMAGE=python:3.12-slim

# ── 1단계: 화면 빌드 ────────────────────────────────────────────────
FROM ${NODE_IMAGE} AS site
# 사내 npm 미러가 필요하면 NPM_REGISTRY 로 지정한다 (비우면 기본 레지스트리)
ARG NPM_REGISTRY=
WORKDIR /src
COPY frontend/package.json frontend/package-lock.json frontend/
RUN if [ -n "$NPM_REGISTRY" ]; then npm config set registry "$NPM_REGISTRY"; fi \
 && cd frontend && npm ci
COPY frontend frontend
COPY site site
# SITE_BASE 없이 빌드 = 서버 주소 바로 아래(/, /chat/, /pages/)에서 제공
RUN cd frontend && npm run build:site -- --out /out

# ── 2단계: 실행 이미지 ──────────────────────────────────────────────
FROM ${PYTHON_IMAGE} AS runtime
# 사내 PyPI 미러가 필요하면 PIP_INDEX_URL 로 지정한다
ARG PIP_INDEX_URL=
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    SITE_DIR=/srv/site
WORKDIR /app
COPY backend/requirements.txt .
RUN pip install --no-cache-dir ${PIP_INDEX_URL:+--index-url "$PIP_INDEX_URL"} -r requirements.txt
COPY backend/app ./app
COPY --from=site /out /srv/site

# root 로 실행하지 않는다
RUN useradd --system --no-create-home --uid 10001 chatpoc
USER chatpoc

EXPOSE 8000
# /health 는 아이디/비밀번호 없이 열려 있다
HEALTHCHECK --interval=30s --timeout=3s --start-period=15s --retries=3 \
  CMD python -c "import sys,urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2).status == 200 else 1)"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
