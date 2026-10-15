"""정적 화면(SITE_DIR) 제공 — 캐시 규칙.

서버를 갱신한 뒤에도 브라우저가 예전 화면을 계속 보여 주는 일을 막는다.
- 화면 파일(html·페이지·그 밖의 모든 파일)은 `no-cache`: 저장은 하되 쓸 때마다 서버에 변경 여부만 물어본다.
  바뀌지 않았으면 304 로 바로 끝나므로 느려지지 않는다 (ETag 는 StaticFiles 가 파일마다 붙여 준다).
- 빌드가 파일 이름에 해시를 붙인 `assets/…-<해시>.js|css` 는 내용이 바뀌면 이름도 바뀌므로 1년 캐시한다.
"""
import re
from typing import Any

from starlette.responses import Response
from starlette.staticfiles import StaticFiles
from starlette.types import Scope

# Vite 가 만든 해시 이름 파일: assets/index-DYBCZKnU.js, assets/index-EDJSh3jJ.css …
_HASHED_ASSET = re.compile(r"(^|/)assets/[^/]+-[A-Za-z0-9_-]{8}\.[A-Za-z0-9]+$")

REVALIDATE = "no-cache"
IMMUTABLE = "public, max-age=31536000, immutable"


def cache_control_for(path: str) -> str:
    """`path` 는 마운트 기준 상대 경로 (예: 'chat/assets/index-DYBCZKnU.js')."""
    return IMMUTABLE if _HASHED_ASSET.search(path.replace("\\", "/")) else REVALIDATE


class CachedStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope: Scope) -> Response:
        response: Any = await super().get_response(path, scope)
        # 200(파일)·304(변경 없음)에만 붙인다. 404 등 오류 응답은 건드리지 않는다.
        if response.status_code in (200, 304):
            response.headers["Cache-Control"] = cache_control_for(path)
        return response
