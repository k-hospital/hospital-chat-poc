"""화면·API 접근 아이디/비밀번호(HTTP Basic). 환경변수 두 개가 모두 있을 때만 켜지고, 없으면 기존처럼 열려 있다.

- CHATBOT_BASIC_USER / CHATBOT_BASIC_PASSWORD : 실행하는 곳(.env 등)에서만 설정한다. 저장소에는 값을 두지 않는다.
- /health 는 컨테이너 상태 확인용이라 인증 없이 열어 둔다.
- 환경변수는 요청마다 읽는다(테스트와 재설정이 쉽도록). 비밀번호는 로그에 남기지 않는다.
"""
import base64
import binascii
import os
import secrets

from starlette.responses import PlainTextResponse
from starlette.types import ASGIApp, Receive, Scope, Send

PUBLIC_PATHS = frozenset({"/health"})


def _credentials() -> tuple[str, str] | None:
    user = os.getenv("CHATBOT_BASIC_USER", "")
    password = os.getenv("CHATBOT_BASIC_PASSWORD", "")
    return (user, password) if user and password else None


def _matches(header: str | None, expected: tuple[str, str]) -> bool:
    if not header or not header.lower().startswith("basic "):
        return False
    try:
        decoded = base64.b64decode(header[6:].strip(), validate=True).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError):
        return False
    user, _, password = decoded.partition(":")
    # 두 값을 모두 비교해 한쪽이 틀렸을 때 걸리는 시간이 달라지지 않게 한다
    ok_user = secrets.compare_digest(user.encode(), expected[0].encode())
    ok_password = secrets.compare_digest(password.encode(), expected[1].encode())
    return ok_user and ok_password


class BasicAuthMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        expected = _credentials()
        # OPTIONS(CORS 사전 요청)는 브라우저가 자격 증명을 붙이지 않으므로 통과시킨다
        if (scope["type"] != "http" or expected is None or scope["path"] in PUBLIC_PATHS
                or scope.get("method") == "OPTIONS"):
            await self.app(scope, receive, send)
            return
        header = next((v.decode("latin-1") for k, v in scope["headers"] if k == b"authorization"), None)
        if _matches(header, expected):
            await self.app(scope, receive, send)
            return
        response = PlainTextResponse("인증이 필요합니다", status_code=401,
                                     headers={"WWW-Authenticate": 'Basic realm="chatpoc", charset="UTF-8"'})
        await response(scope, receive, send)
