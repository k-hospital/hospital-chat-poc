"""정적 화면(SITE_DIR) 캐시 헤더 — 화면 파일은 항상 최신본을 확인하고, 해시가 붙은 파일만 오래 캐시한다.

서버를 갱신한 뒤 팀원이 캐시를 따로 지우지 않아도 새 화면이 보이게 하기 위한 규칙이다.
"""
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.static_site import CachedStaticFiles


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    files = {
        "index.html": "<html>main</html>",
        "chat/index.html": "<html>chat</html>",
        "chat/assets/index-DYBCZKnU.js": "console.log(1)",
        "chat/assets/index-EDJSh3jJ.css": "body{}",
        "chat/assets/logo.png": "png",              # 해시가 없는 파일
        "pages/health-checkup.html": "<html>page</html>",
        "favicon.svg": "<svg/>",
    }
    for name, body in files.items():
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    app = FastAPI()
    app.mount("/", CachedStaticFiles(directory=tmp_path, html=True), name="site")
    return TestClient(app)


@pytest.mark.parametrize("path", ["/", "/chat/", "/chat/index.html", "/pages/health-checkup.html", "/favicon.svg"])
def test_screens_are_revalidated_every_time(client, path):
    res = client.get(path)
    assert res.status_code == 200
    assert res.headers["cache-control"] == "no-cache"


@pytest.mark.parametrize("path", ["/chat/assets/index-DYBCZKnU.js", "/chat/assets/index-EDJSh3jJ.css"])
def test_hashed_assets_are_cached_for_a_long_time(client, path):
    res = client.get(path)
    assert res.status_code == 200
    assert res.headers["cache-control"] == "public, max-age=31536000, immutable"


def test_assets_without_a_hash_are_not_cached_forever(client):
    res = client.get("/chat/assets/logo.png")
    assert res.status_code == 200
    assert res.headers["cache-control"] == "no-cache"


def test_unchanged_file_is_answered_with_304_and_keeps_the_header(client):
    first = client.get("/chat/")
    etag = first.headers["etag"]
    second = client.get("/chat/", headers={"If-None-Match": etag})
    assert second.status_code == 304
    assert second.headers["cache-control"] == "no-cache"


def test_missing_file_is_404(client):
    assert client.get("/chat/assets/index-ZZZZZZZZ.js").status_code == 404
